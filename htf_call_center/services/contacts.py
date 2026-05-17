"""contacts service — bridge res.partner ↔ Hatif contact.

`upsert_from_partner(partner)`:
    Looks for an existing link, then either POST `/v1/contacts` to
    create or PUT `/v1/contacts/{id}` to update. Stores the resulting
    Hatif contact id on `htf.contact.link` and mirrors it onto
    `res.partner.x_htf_contact_id` for fast filtering.

`sync_from_htf(htf_contact_id)`:
    Pulls a Hatif contact by id and upserts the local partner.

Phone numbers are normalized to E.164 at the boundary via `utils/phone`.
Non-normalizable numbers are sent as-is to Hatif (it'll reject them
loudly), so we don't silently drop user input.
"""

from __future__ import annotations

import logging

from odoo import fields

from ..exceptions import HtfNotFoundError, HtfValidationError
from ..utils.phone import normalize_e164

_logger = logging.getLogger(__name__)


class ContactService:
    name = 'contacts'

    def __init__(self, env):
        self.env = env

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _partner_to_payload(self, partner) -> dict:
        phone = partner.phone or partner.mobile
        e164 = normalize_e164(phone) if phone else None
        return {
            'name': partner.name or '',
            'phoneNumber': e164 or phone or '',
            'email': partner.email or '',
        }

    def _apply_hatif_to_partner(self, partner, htf_contact: dict) -> None:
        """Mutate an Odoo partner from a Hatif contact payload."""
        updates = {}
        name = (htf_contact.get('name') or '').strip()
        if name and name != partner.name:
            updates['name'] = name
        email = (htf_contact.get('email') or '').strip().lower()
        if email and email != (partner.email or '').lower():
            updates['email'] = email
        phone_raw = htf_contact.get('phoneNumber') or htf_contact.get('phone')
        if phone_raw:
            normalized = normalize_e164(phone_raw) or phone_raw
            if normalized != partner.phone:
                updates['phone'] = normalized
        if updates:
            partner.write(updates)

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def upsert_from_partner(self, partner):
        """Push a partner to Hatif, return the htf.contact.link record."""
        if not partner:
            raise HtfValidationError('upsert_from_partner requires a partner')
        Link = self.env['htf.contact.link'].sudo()
        http = self.env['htf.config'].get_service('http')
        now = fields.Datetime.now()
        link = Link.search([('partner_id', '=', partner.id)], limit=1)
        payload = self._partner_to_payload(partner)

        if link and link.htf_contact_id:
            result = http.put(f'/v1/contacts/{link.htf_contact_id}', json_body=payload)
            link.write({
                'last_synced_at': now,
                'sync_state': 'synced',
                'sync_error': False,
            })
        else:
            result = http.post('/v1/contacts', json_body=payload) or {}
            htf_id = result.get('id') or result.get('contactId')
            if not htf_id:
                raise HtfValidationError(
                    'Hatif contact create response missing id',
                    body=str(result)[:300],
                )
            if link:
                link.write({
                    'htf_contact_id': htf_id,
                    'last_synced_at': now,
                    'sync_state': 'synced',
                    'sync_error': False,
                })
            else:
                link = Link.create({
                    'partner_id': partner.id,
                    'htf_contact_id': htf_id,
                    'last_synced_at': now,
                    'sync_state': 'synced',
                })

        # Mirror to denorm field for fast filter.
        partner.sudo().write({
            'x_htf_contact_id': link.htf_contact_id,
            'x_htf_synced_at': now,
        })
        return link

    def sync_from_htf(self, htf_contact_id: str):
        """Pull a Hatif contact and upsert the local partner."""
        if not htf_contact_id:
            raise HtfValidationError('sync_from_htf requires a contact id')
        http = self.env['htf.config'].get_service('http')
        contact = http.get(f'/v1/contacts/{htf_contact_id}')
        if not contact:
            raise HtfNotFoundError(f'Contact {htf_contact_id!r} not found on Hatif')

        Link = self.env['htf.contact.link'].sudo()
        Partner = self.env['res.partner'].sudo()
        link = Link.search([('htf_contact_id', '=', htf_contact_id)], limit=1)
        now = fields.Datetime.now()

        if link:
            self._apply_hatif_to_partner(link.partner_id, contact)
            link.write({
                'last_synced_at': now,
                'sync_state': 'synced',
                'sync_error': False,
            })
            return link

        # No link yet — try to find a partner by E.164 phone match.
        e164 = normalize_e164(contact.get('phoneNumber') or contact.get('phone'))
        partner = False
        if e164:
            partner = Partner.search([
                '|', ('phone', '=', e164), ('mobile', '=', e164),
            ], limit=1)
        if not partner:
            partner = Partner.create({
                'name': (contact.get('name') or e164 or htf_contact_id).strip(),
                'phone': e164 or contact.get('phoneNumber') or False,
                'email': (contact.get('email') or '').strip().lower() or False,
            })
        else:
            self._apply_hatif_to_partner(partner, contact)

        link = Link.create({
            'partner_id': partner.id,
            'htf_contact_id': htf_contact_id,
            'last_synced_at': now,
            'sync_state': 'synced',
        })
        partner.write({
            'x_htf_contact_id': htf_contact_id,
            'x_htf_synced_at': now,
        })
        return link

    def delete(self, partner) -> None:
        link = self.env['htf.contact.link'].sudo().search([
            ('partner_id', '=', partner.id),
        ], limit=1)
        if not link:
            return
        http = self.env['htf.config'].get_service('http')
        try:
            http.delete(f'/v1/contacts/{link.htf_contact_id}')
        except HtfNotFoundError:
            _logger.info(
                "[htf.contacts] hatif already gone for partner %s; clearing link",
                partner.id,
            )
        link.unlink()
        partner.sudo().write({'x_htf_contact_id': False})
