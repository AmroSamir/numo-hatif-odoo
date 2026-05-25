"""discuss.channel extension for P7 — Hatif conversation surface.

Adds 3 fields that mark a `discuss.channel` as a "Hatif-linked" channel:
one channel per `res.partner` with Hatif activity. The channel is created
lazily by services/whatsapp_inbound.py + services/calls.py on first
inbound webhook for that partner. With the master flag
`htf_call_center.discuss_mirror_enabled` off, these fields stay empty and
no codepath in the module touches discuss.channel.

The schema is additive only — every field is nullable, has a safe
default, and is unreferenced when the feature flag is off, so dropping
this file in a revert leaves the columns harmless.

P7.5 patches the OWL ChatWindow component to look at `x_htf_partner_id`
to decide whether to hide the native voice-call icon and render the
"Call via Hatif" button. With `discuss_ui_override=False`, the patch is
a no-op and the field is read but ignored.
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import timedelta

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
from odoo.tools import html2plaintext

from ..exceptions import HtfDncBlockedError, HtfWindowExpiredError

_logger = logging.getLogger(__name__)


# Cache the encoded logo so we don't re-read + re-encode it on every
# channel auto-creation. Loaded lazily on first use.
_HATIF_LOGO_CACHE: bytes | None = None


def _hatif_logo_b64() -> bytes | None:
    """Return base64-encoded Hatif logo, or None if the file is missing."""
    global _HATIF_LOGO_CACHE
    if _HATIF_LOGO_CACHE is not None:
        return _HATIF_LOGO_CACHE
    here = os.path.dirname(__file__)
    path = os.path.normpath(os.path.join(
        here, '..', 'static', 'src', 'img', 'hatif-logo.png',
    ))
    try:
        with open(path, 'rb') as f:
            _HATIF_LOGO_CACHE = base64.b64encode(f.read())
        return _HATIF_LOGO_CACHE
    except OSError:
        _logger.warning("[htf-discuss] hatif-logo.png missing at %s", path)
        return None

# Hard dedup window for the outbound override.
#
# Two distinct failure modes this guards against:
#   1. Discuss voice-recording composer firing message_post 8+ times
#      for a single user action (recording + concurrent typed text +
#      send) — original reason for the guard.
#   2. User clicking Send a second/third time after the first call
#      appears to hang (e.g. because Hatif's response is slow). Each
#      click is a fresh message_post → would be a fresh send. 30s is
#      well above Hatif's typical 5-15s response window so the second
#      click is reliably dedup'd, while still narrow enough that a
#      legitimate same-body reply 30s later isn't blocked.
_OUTBOUND_DEDUP_SECONDS = 30


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    # The customer this channel represents. NULL on every standard
    # Odoo channel (DMs, internal channels, livechat, etc.) — only
    # set on auto-provisioned Hatif mirror channels. Indexed so the
    # OWL patch's `t-if` on x_htf_partner_id is cheap, and so the
    # revert tooling can find every Hatif-linked channel in one query.
    x_htf_partner_id = fields.Many2one(
        'res.partner',
        string='Hatif Customer',
        copy=False,
        index=True,
        ondelete='set null',
        help='Set when this channel is the per-partner mirror of '
             'Hatif activity. NULL on every standard Odoo channel.',
    )
    # Most recent conversationId observed on any webhook for this
    # partner. Used by the OWL ChatWindow patch to build the
    # "Call via Hatif" deep-link `app.hatif.io/ar/inbox?conversationId=<id>`.
    x_htf_last_conversation_id = fields.Char(
        string='Last Hatif conversationId',
        copy=False,
        help='Updated on every webhook. Empty until the first webhook '
             'lands for this partner.',
    )
    # Most recent Hatif channel (the workspace channel like
    # "أكاديمية نمو" or "الدعم الفني") this conversation flowed
    # through. Used when the outbound override needs to pick which
    # Hatif channel to send a reply on — falls back to the existing
    # resolver chain when empty.
    x_htf_last_htf_channel_id = fields.Many2one(
        'htf.channel',
        string='Last Hatif Channel Used',
        copy=False,
        ondelete='set null',
        help='Updated on every webhook. Tells the outbound override '
             'which Hatif channel to route the agent reply through.',
    )
    # Flat Char proxy for the raw Hatif UUID — `_to_store_defaults`
    # serializes field names to the OWL store, and a Many2one would
    # arrive as `[id, name]` which the JS deep-link builder would have
    # to unpack. Exposing the UUID as a plain string keeps the JS
    # side trivially `?channelId=${x_htf_last_channel_uuid}`.
    x_htf_last_channel_uuid = fields.Char(
        related='x_htf_last_htf_channel_id.htf_channel_id',
        string='Last Hatif channelId (UUID)',
        readonly=True,
        store=False,
    )
    # v19.0.1.40.0 — channel-level inbound timestamp. Stamped by the
    # INBOUND mirror whenever a customer message lands in this channel,
    # REGARDLESS of which exact res.partner record authored it. This is
    # the robust source of truth for the 24h window in the Discuss
    # composer: relying on author-id == x_htf_partner_id breaks when
    # phone-format variations create duplicate partner records (the
    # inbound webhook resolves to partner B while the channel was
    # provisioned for partner A — same human, two rows). The channel
    # always knows when IT last received inbound traffic.
    x_htf_last_inbound_at = fields.Datetime(
        string='Last Inbound At (channel)',
        copy=False,
        help='When this channel last received an inbound WhatsApp '
             'message. Drives the composer 24h-window gate. Set by the '
             'inbound discuss mirror; pushed to the OWL store reactively.',
    )

    # ------------------------------------------------------------------ #
    # P7.5 — Push x_htf fields to the OWL store                          #
    # ------------------------------------------------------------------ #
    # The OWL ChatWindow patch reads `thread.x_htf_partner_id` to decide
    # whether to hide the native voice-call buttons and render the
    # "Call via Hatif" anchor. Without this _to_store_defaults override
    # the fields stay server-side and the patch sees `undefined`.
    #
    # Gated by the `discuss_ui_override` sub-flag — turning it off
    # makes the OWL patch see undefined on every channel, so the
    # native UI returns even though the schema + mirror are still
    # active. This is the L2 revert path for the OWL surface alone.

    def _to_store_defaults(self, target):
        base = super()._to_store_defaults(target)
        if self.env['htf.config'].discuss_mirror_active('ui'):
            return base + [
                'x_htf_partner_id',
                'x_htf_last_conversation_id',
                'x_htf_last_channel_uuid',
                'x_htf_last_inbound_at',
            ]
        return base

    def _htf_stamp_inbound_now(self, when=None):
        """Stamp x_htf_last_inbound_at and push it to the OWL store so
        connected composers re-evaluate their 24h-window gate within
        ~1-2 seconds, without a page refresh.

        Called by the inbound discuss mirror. ``when`` defaults to now;
        callers can pass the message's created_at for accuracy.
        """
        self.ensure_one()
        from odoo.addons.mail.tools.discuss import Store
        ts = when or fields.Datetime.now()
        self.sudo().write({'x_htf_last_inbound_at': ts})
        try:
            Store(bus_channel=self).add(
                self, {'x_htf_last_inbound_at': ts},
            ).bus_send()
        except Exception:  # noqa: BLE001 — push is best-effort; DB write already done
            _logger.exception(
                "[htf-discuss] bus push of x_htf_last_inbound_at failed "
                "for channel=%s", self.id,
            )

    # ------------------------------------------------------------------ #
    # Channel auto-provisioning                                          #
    # ------------------------------------------------------------------ #

    @api.model
    def _ensure_htf_discuss_channel(self, partner):
        """Get-or-create the per-partner Hatif Discuss channel.

        Idempotent. Returns the channel record. CALLER MUST CHECK the
        master feature flag before calling — this method assumes it is
        on and proceeds unconditionally.

        Channel shape (decisions locked 2026-05-19):
          - channel_type='group' (PRIVATE — invite-only, NOT listed in
            the Channels directory; a 'channel' type is publicly
            discoverable + joinable by any internal user, which leaked
            every customer's chat to every agent — v19.0.1.60.0)
          - name = f"Hatif · {partner.display_name}"
          - members: the partner (so their name + avatar render on
            inbound bubbles via author_id=partner.id)
          - x_htf_partner_id = partner.id (this is what the OWL patch
            and revert tooling look for)
        """
        if not partner:
            return self.env['discuss.channel']
        # Fast path — back-reference on the partner.
        if partner.x_htf_discuss_channel_id and partner.x_htf_discuss_channel_id.active:
            return partner.x_htf_discuss_channel_id
        # Slow path — orphan-search by x_htf_partner_id (handles the case
        # where partner.x_htf_discuss_channel_id got cleared somehow).
        existing = self.sudo().search(
            [('x_htf_partner_id', '=', partner.id), ('active', '=', True)], limit=1,
        )
        if existing:
            if not partner.x_htf_discuss_channel_id:
                partner.sudo().write({'x_htf_discuss_channel_id': existing.id})
            return existing
        # Create. Channel name = just the partner display_name; the
        # Hatif-branded image_128 below is what makes the row visually
        # distinct in the Discuss sidebar (we used to prefix with 📞
        # but the channel image is a cleaner solution).
        channel_name = partner.display_name or partner.name or 'Hatif Customer'
        channel = self.sudo().create({
            'name': channel_name[:200],  # mail enforces 200-char cap somewhere
            # 'group' = private, invite-only, hidden from the Channels
            # directory. 'channel' was publicly discoverable/joinable.
            'channel_type': 'group',
            'x_htf_partner_id': partner.id,
            'image_128': _hatif_logo_b64(),
        })
        # Seed the channel with only the AUTHORISED members:
        #   - the customer's partner (always — needed so author_id
        #     rendering on inbound bubbles attributes to their name +
        #     avatar; they have no res.users, they never log in)
        #   - every user in htf_call_center.group_admin (Hatif admins)
        #   - every user who is the salesperson on a CRM lead linked
        #     to this partner (the agents actually working the customer)
        # Other internal users are NOT auto-added — a customer's
        # conversation should only be visible to the agents handling
        # them, not the whole workspace.
        allowed_partner_ids = self._htf_allowed_member_partner_ids(partner)
        Member = self.env['discuss.channel.member'].sudo()
        # Odoo's discuss.channel create can auto-add the creating user
        # as a member (so they see the new channel in their sidebar).
        # Skip any partner that's already in the channel's membership
        # to avoid violating the (channel_id, partner_id) unique
        # constraint when our allowed set overlaps with the auto-adds.
        already_members = {m.partner_id.id for m in channel.channel_member_ids}
        for pid in allowed_partner_ids - already_members:
            Member.create({'channel_id': channel.id, 'partner_id': pid})
        partner.sudo().write({'x_htf_discuss_channel_id': channel.id})
        _logger.info(
            "[htf-discuss] auto-provisioned channel id=%s for partner id=%s (%s) "
            "with %d initial member(s)",
            channel.id, partner.id, partner.display_name,
            len(allowed_partner_ids),
        )
        return channel

    @api.model
    def _htf_allowed_member_partner_ids(self, partner):
        """Return the set of ``res.partner`` ids allowed to see the Hatif
        Discuss channel for ``partner``.

        Access rule (v19.0.1.61.0) — a customer's conversation is private
        to the people working them:
          • the customer (always — inbound bubbles author as this partner)
          • the agent(s) who contacted them: the salesperson
            (``crm.lead.user_id``) on the customer's CRM lead(s)
          • each such agent's sales-team leader (``crm.team.user_id`` of
            the team the agent leads or belongs to, plus the lead's own
            team leader)
          • managers: Odoo Sales Managers (``sales_team.group_sale_manager``)
            see every chat — EXCEPT a manager who is the leader of a
            DIFFERENT team. In this DB every team leader also holds the
            Sales Manager role, so a blanket "managers see all" leaked a
            customer's chat to every other team's leader. A manager who
            leads no team (a true global manager) still sees everything;
            a team leader only sees their OWN team's customers.

        Nobody else. Single source of truth shared by the
        auto-provisioning code, the CRM-lead write hook, and the prune
        tool. Enforced by ``_htf_sync_channel_members`` (adds + removes)
        and by the channel being a private ``group`` type.
        """
        allowed = set()
        if not partner:
            return allowed
        allowed.add(partner.id)

        Team = self.env['crm.team'].sudo()
        # Every user who leads ANY team — used to spot "other-team" leaders.
        all_team_leader_uids = set(
            Team.search([('user_id', '!=', False)]).mapped('user_id').ids
        )

        # Agents on this customer's leads, plus their own team leaders.
        agent_team_leader_uids = set()
        leads = self.env['crm.lead'].sudo().search([
            ('partner_id', '=', partner.id),
        ])
        for lead in leads:
            agent = lead.user_id
            if not agent or not agent.partner_id:
                continue
            allowed.add(agent.partner_id.id)
            # The agent's sales-team leader(s): teams the agent leads or
            # is a member of, plus the lead's own team.
            teams = Team.search([('user_id', '=', agent.id)])
            if lead.team_id:
                teams |= lead.team_id
            try:
                memberships = self.env['crm.team.member'].sudo().search([
                    ('user_id', '=', agent.id),
                ])
                teams |= memberships.mapped('crm_team_id')
            except Exception:  # noqa: BLE001 — membership model optional
                pass
            for team in teams:
                if team.user_id and team.user_id.partner_id:
                    allowed.add(team.user_id.partner_id.id)
                    agent_team_leader_uids.add(team.user_id.id)

        # Managers — Sales Managers see every chat, EXCEPT a manager who
        # leads a team OTHER than this customer's agent team(s). Pure
        # managers (lead no team) and the agent's own team leader stay.
        mgr_group = self.env.ref(
            'sales_team.group_sale_manager', raise_if_not_found=False,
        )
        if mgr_group:
            for u in mgr_group.user_ids:
                if not u.partner_id:
                    continue
                leads_other_team = (
                    u.id in all_team_leader_uids
                    and u.id not in agent_team_leader_uids
                )
                if leads_other_team:
                    continue
                allowed.add(u.partner_id.id)
        return allowed

    def _htf_sync_channel_members(self):
        """Recompute and apply the authorised member set for this
        channel. Called from the CRM-lead salesperson-change hook so
        a re-assigned lead pulls the new agent INTO the channel and
        drops the old one OUT.
        """
        Member = self.env['discuss.channel.member'].sudo()
        for ch in self:
            if not ch.x_htf_partner_id:
                continue
            allowed = ch._htf_allowed_member_partner_ids(ch.x_htf_partner_id)
            current = {m.partner_id.id: m for m in ch.channel_member_ids}
            # Add missing
            for pid in allowed - set(current):
                Member.create({'channel_id': ch.id, 'partner_id': pid})
            # Remove excess
            extras = [m for pid, m in current.items() if pid not in allowed]
            if extras:
                Member.browse([m.id for m in extras]).unlink()

    # ------------------------------------------------------------------ #
    # P7.4 — Outbound override                                           #
    # ------------------------------------------------------------------ #
    # When an internal Odoo user types in a Hatif-linked channel, route
    # the message body through Hatif WhatsApp outbound after the
    # message is persisted. Guards:
    #   1. Channel must have x_htf_partner_id set.
    #   2. Master flag + outbound sub-flag must be on.
    #   3. The context flag `htf_mirror_write` is NOT set (which is
    #      what our own mirror writes from services/discuss_mirror.py
    #      use to avoid an infinite loop).
    #   4. The message author is NOT the partner (i.e. it's not an
    #      inbound mirror from a customer-as-author write).
    #   5. The message subtype is NOT the htf-mirror sentinel.
    #
    # 24h-window check fails -> UserError -> Odoo rolls back the
    # transaction (the persisted mail.message is undone) and OWL shows
    # the error toast. This honors locked decision 5(a): "reject with
    # toast" (no auto-template injection).

    def _message_post_after_hook(self, message, msg_vals):
        # Always call super() FIRST so non-Hatif channels are not
        # affected and the base bookkeeping (notification, bus, etc.)
        # runs unaffected.
        result = super()._message_post_after_hook(message, msg_vals)
        try:
            if not self._htf_should_route_outbound(message, msg_vals):
                return result
            self._htf_send_outbound_via_hatif(message)
        except UserError:
            raise
        except Exception:  # noqa: BLE001 — never lose an error to logs
            _logger.exception(
                "[htf-discuss] outbound route failed for channel=%s message=%s",
                self.id, message.id,
            )
            raise UserError(
                _('WhatsApp send via Hatif failed — see server logs for details.')
            ) from None
        return result

    def _htf_should_route_outbound(self, message, msg_vals) -> bool:
        """Five-gate check for the outbound override. All must be True."""
        # 1. Hatif-linked channel
        if not self.x_htf_partner_id:
            return False
        # 2. Master + sub-flag
        if not self.env['htf.config'].discuss_mirror_active('outbound'):
            return False
        # 3. Not our own mirror write
        if self.env.context.get('htf_mirror_write'):
            return False
        # 4. Not authored by the partner (=inbound mirror)
        if message.author_id and message.author_id == self.x_htf_partner_id:
            return False
        # 5. Not the mt_htf_mirror sentinel subtype
        mirror_subtype = self.env.ref(
            'htf_call_center.mt_htf_mirror', raise_if_not_found=False
        )
        if message.subtype_id and mirror_subtype and message.subtype_id == mirror_subtype:
            return False
        # Only route messages with actual text. Voice notes, file uploads,
        # and pure attachment posts are routed only when there's body text.
        # (Hatif voice/audio outbound isn't in scope for P7.)
        plain = html2plaintext(message.body or '').strip()
        if not plain:
            return False
        # 6. Anti-burst dedup — defends against the Discuss voice-recording
        # UI firing message_post multiple times for one user action.
        # If the same author posted the same body to this channel within
        # the dedup window, skip — Hatif has already received the first
        # send, the duplicates are noise.
        cutoff = fields.Datetime.now() - timedelta(seconds=_OUTBOUND_DEDUP_SECONDS)
        recent = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'),
            ('res_id', '=', self.id),
            ('author_id', '=', message.author_id.id),
            ('id', '!=', message.id),
            ('create_date', '>=', cutoff),
        ], limit=20, order='id desc')
        for prev in recent:
            if html2plaintext(prev.body or '').strip() == plain:
                _logger.info(
                    "[htf-discuss] outbound dedup-skip — same body in "
                    "channel=%s author=%s within %ds (prev msg=%s)",
                    self.id, message.author_id.id,
                    _OUTBOUND_DEDUP_SECONDS, prev.id,
                )
                return False
        return True

    def _htf_send_outbound_via_hatif(self, message):
        """Send the message body through Hatif WhatsApp outbound.

        Errors raise UserError so OWL renders the toast and Odoo rolls
        back the persisted mail.message. This is the locked-decision-5(a)
        path: window-closed = explicit rejection, not silent fallback.
        """
        from ..services import whatsapp  # local import to avoid cycle at boot
        partner = self.x_htf_partner_id
        if not partner:
            raise UserError(_('Hatif channel has no partner — cannot send.'))
        phone = partner.phone or ''  # Odoo 19 dropped res.partner.mobile
        if not phone:
            raise UserError(
                _('Partner %s has no phone number — cannot send WhatsApp.')
                % partner.display_name
            )
        plain_body = html2plaintext(message.body or '').strip()
        if not plain_body:
            raise UserError(_('Empty message body — nothing to send.'))
        # v19.0.1.41.0: route the reply through the SAME Hatif channel
        # the conversation has been using (stamped on the discuss
        # channel as x_htf_last_htf_channel_id) instead of re-resolving
        # through the team-default chain. A reply belongs on the channel
        # the customer contacted us through — and re-resolution fails
        # outright when the partner's team has no default WA channel
        # (HtfChannelNotFoundError), which is what produced the ⚠️
        # send-failures on free-form replies. Falls back to the
        # resolver chain (channel=None) only when the conversation has
        # no recorded channel yet.
        htf_channel = self.x_htf_last_htf_channel_id or None
        # v19.0.1.42.0: gate the 24h window on the CHANNEL's inbound
        # timestamp, not the partner's. send_text._check_window reads
        # partner.x_htf_24h_window_open, which is wrong under duplicate
        # partner records (inbound updated partner B's window while this
        # conversation is anchored on partner A — see v40). The channel
        # timestamp is the authoritative signal and matches exactly what
        # the composer UI used to decide the input was typeable. If the
        # channel window is closed, reject with the template-required
        # toast; otherwise tell send_text to skip its partner-based check.
        chan_open = bool(
            self.x_htf_last_inbound_at
            and self.x_htf_last_inbound_at
            >= fields.Datetime.now() - timedelta(hours=24)
        )
        if not chan_open:
            raise UserError(_(
                "Template message required\n\n"
                "To start or resume a conversation, you must send an "
                "approved Meta template message. Once the customer "
                "replies, you can message freely for 24 hours.\n\n"
                "يلزم إرسال قالب رسالة\n\n"
                "لبدء المحادثة أو استئنافها، يجب إرسال قالب رسالة "
                "معتمد من Meta. بعد رد العميل، ستتمكن من الكتابة "
                "بحرية لمدة 24 ساعة."
            ))
        # v19.0.1.52.0: VALIDATE + persist the pending htf.message row
        # synchronously (so a DNC/window failure still rolls the bubble
        # back via UserError), but DEFER the Hatif HTTP POST to a
        # post-commit hook. The POST used to run inside this message_post
        # transaction; Hatif fires its delivery-status echo webhook the
        # instant it receives the send, and that webhook writes the SAME
        # discuss.channel row, so this transaction hit SerializationFailure
        # and Odoo retried it. On retry the autonomous dedup claim
        # suppressed the "resend", so the agent's own bubble was dropped
        # and the echo re-created it as an OdooBot mirror (the duplicate
        # bubble + ⚠️ the agent saw). A post-commit send fires EXACTLY
        # ONCE after this transaction commits — Odoo discards the
        # post-commit callbacks of a rolled-back attempt — so there is no
        # race with the echo and no double-send on retry.
        try:
            htf_msg, endpoint, body = whatsapp.prepare_text_send(
                self.env, to_number=phone, text=plain_body, partner=partner,
                channel=htf_channel, skip_window_check=True,
            )
        except HtfDncBlockedError:
            raise UserError(_(
                'This partner has opted out (DNC). WhatsApp send blocked.'
            )) from None
        except HtfWindowExpiredError:
            raise UserError(_(
                "Template message required\n\n"
                "To start or resume a conversation, you must send an "
                "approved Meta template message. Once the customer "
                "replies, you can message freely for 24 hours.\n\n"
                "يلزم إرسال قالب رسالة\n\n"
                "لبدء المحادثة أو استئنافها، يجب إرسال قالب رسالة "
                "معتمد من Meta. بعد رد العميل، ستتمكن من الكتابة "
                "بحرية لمدة 24 ساعة."
            )) from None
        # Tag the agent's composer bubble with the mirror sentinel so the
        # echo webhook's mirror_outbound_wa_from_hatif skips it (no
        # duplicate OdooBot-authored copy).
        try:
            message.sudo().write({
                'message_id': f'<htf-msg-{htf_msg.id}@htf_call_center>',
            })
        except Exception:  # noqa: BLE001 — non-critical
            _logger.exception(
                "[htf-discuss] could not tag mail.message=%s with htf-msg sentinel",
                message.id,
            )
        # Defer the Hatif POST to after this transaction commits.
        msg_id = htf_msg.id
        channel_id = self.id
        dedup_body = plain_body
        dispatch_kwargs = {
            'endpoint': endpoint,
            'body': body,
            'partner_id': partner.id,
            'channel_id': htf_channel.id if htf_channel else False,
        }
        registry = self.env.registry

        def _send_after_commit():
            try:
                with registry.cursor() as cr:
                    post_env = api.Environment(cr, SUPERUSER_ID, {})
                    # The dedup claim lives INSIDE the post-commit hook so a
                    # serialization-retry of the message_post transaction
                    # (whose post-commit callbacks were discarded on
                    # rollback) can never suppress the one real send.
                    if not post_env['htf.outbound.dedup']._htf_claim_send(
                        channel_id, dedup_body,
                    ):
                        return
                    whatsapp.dispatch_prepared(
                        post_env, msg_id, skip_discuss_mirror=True,
                        **dispatch_kwargs,
                    )
                    cr.commit()
            except Exception:  # noqa: BLE001 — a post-commit hook must never raise
                _logger.exception(
                    "[htf-discuss] deferred outbound send failed for "
                    "htf.message=%s channel=%s", msg_id, channel_id,
                )

        self.env.cr.postcommit.add(_send_after_commit)
