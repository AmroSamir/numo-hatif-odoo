"""Import vCards wizard — bulk push contacts from a pasted vCard blob.

Posts to Hatif's `/v1/contacts/import/vcards`. Each contact in the blob
maps to a Hatif contact; we do NOT auto-create local res.partners here
(use the per-row sync flow if needed). Returns counts of
created / updated / errors.
"""

from __future__ import annotations

import base64
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HtfImportVcardsWizard(models.TransientModel):
    _name = 'htf.import.vcards.wizard'
    _description = 'Import vCards into Hatif'

    paste_blob = fields.Text(
        string='Paste vCards',
        help='Paste one or more vCard blocks here. Each begins with '
             'BEGIN:VCARD and ends with END:VCARD.',
    )
    file_data = fields.Binary(string='Upload file')
    file_name = fields.Char(string='Filename')
    result_summary = fields.Char(readonly=True)
    result_detail = fields.Text(readonly=True)

    def _gather_blob(self) -> str:
        if self.file_data:
            try:
                return base64.b64decode(self.file_data).decode('utf-8', errors='replace')
            except Exception as exc:
                raise UserError(_('Could not decode uploaded file: %s') % exc) from exc
        return (self.paste_blob or '').strip()

    def action_import(self):
        self.ensure_one()
        blob = self._gather_blob()
        if not blob:
            raise UserError(_('Paste or upload at least one vCard first.'))

        http = self.env['htf.config'].get_service('http')
        result = http.post(
            '/v1/contacts/import/vcards',
            json_body={'vcards': blob},
        ) or {}

        created = int(result.get('created') or 0)
        updated = int(result.get('updated') or 0)
        errors = result.get('errors') or []
        self.write({
            'result_summary': _('%(c)s created, %(u)s updated, %(e)s errors') % {
                'c': created, 'u': updated, 'e': len(errors),
            },
            'result_detail': '\n'.join(str(e) for e in errors) or _('All rows processed cleanly.'),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
