"""htf.call — voice call record (inbound or outbound, completed or missed).

Per DATA_MODEL.md and Hatif's Call Webhook payload (apidog L4826+).

Lifecycle:
1. Hatif call ends → POST to ``controllers/webhook_call.py``
2. ``services/calls.py`` creates/updates ``htf.call`` row
3. ``services/chatter.py.post_call()`` posts a bubble to the partner
   chatter showing duration / status / recording link / Summary preview
4. Fires one of: ``htf.call.received`` (status=Completed),
   ``htf.call.missed`` (status in Missed/NoAnswer/RejectedByCallee/
   Cancelled), or ``htf.call.failed`` (status=Failed).

Transcription, AI summary, sentiment, and evaluation rubric come in
the SAME webhook payload — Hatif's analytics layer runs them before
the post-call delivery. We store them on the htf.call row directly so
P9 (LLM via n8n) can replay them later.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


# Hatif → Odoo selection mappings ------------------------------------- #

# status int → label (apidog enum)
HATIF_STATUS_MAP = {
    0: 'active',
    1: 'completed',
    2: 'missed',
    3: 'rejected_by_caller',
    4: 'rejected_by_callee',
    5: 'no_answer',
    6: 'cancelled',
    7: 'failed',
}

# type int → direction (apidog enum)
HATIF_DIRECTION_MAP = {
    1: 'inbound',
    2: 'outbound',
}

# sentiment int → label (apidog enum)
HATIF_SENTIMENT_MAP = {
    1: 'positive',
    2: 'neutral',
    3: 'negative',
    4: 'mixed',
    5: 'unknown',
}

# status buckets used by signal dispatch + UI badges
MISSED_STATUSES = {'missed', 'no_answer', 'rejected_by_callee', 'cancelled'}
COMPLETED_STATUSES = {'completed'}
FAILED_STATUSES = {'failed'}


class HtfCall(models.Model):
    _name = 'htf.call'
    _description = 'HTF Voice Call'
    _order = 'created_at desc, id desc'
    _rec_name = 'name'
    _log_access = True

    # Display / identity ---------------------------------------------- #
    name = fields.Char(compute='_compute_name', store=True)
    htf_call_id = fields.Char(
        string='Hatif Call ID',
        index=True,
        help='Vendor-side call identifier. Used as the idempotency key '
             'when the webhook controller dedupes Hatif retries.',
    )
    workspace_uuid = fields.Char(
        string='Hatif Workspace UUID',
        index=True,
        help='Raw workspaceId from the webhook payload.',
    )
    contact_uuid = fields.Char(
        string='Hatif Contact UUID',
        index=True,
    )

    # Routing --------------------------------------------------------- #
    direction = fields.Selection(
        selection=[
            ('inbound', 'Inbound'),
            ('outbound', 'Outbound'),
        ],
        required=True,
        index=True,
    )
    status = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('missed', 'Missed'),
            ('rejected_by_caller', 'Rejected by Caller'),
            ('rejected_by_callee', 'Rejected by Callee'),
            ('no_answer', 'No Answer'),
            ('cancelled', 'Cancelled'),
            ('failed', 'Failed'),
        ],
        required=True,
        index=True,
    )

    # Phone numbers — stored as-arrived; partner resolution via E.164 norm.
    caller_number = fields.Char(string='Caller Number')
    callee_number = fields.Char(string='Callee Number')
    contact_number = fields.Char(
        string='Contact Phone (from Hatif)',
        help='Phone Hatif believes the contact owns — may differ from '
             'caller_number/callee_number in transfer scenarios.',
    )

    # Timing ---------------------------------------------------------- #
    created_at = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        index=True,
        help='Hatif creationTime — when their server first recorded the '
             'call object. Not the Odoo create_date (which tracks when '
             'the bridge persisted the row).',
    )
    pickup_time = fields.Datetime(
        help='When the call was answered (null for missed / no-answer).',
    )
    hangup_time = fields.Datetime()
    duration_seconds = fields.Integer(
        compute='_compute_duration',
        store=True,
        help='Computed from pickup_time → hangup_time. Falls back to '
             'parsing call_length_raw (HH:MM:SS) when timestamps missing.',
    )
    duration_display = fields.Char(
        compute='_compute_duration_display',
        store=False,
        help='Human-readable duration: "0:32" / "5:32" / "1:05:32". '
             'Use this in views — NEVER use widget="float_time" on '
             'duration_seconds (it interprets the integer as hours).',
    )
    call_length_raw = fields.Char(
        string='Call Length (raw)',
        help='Hatif callLength HH:MM:SS string preserved for debug.',
    )

    # Participants ---------------------------------------------------- #
    channel_id = fields.Many2one(
        'htf.channel',
        ondelete='restrict',
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        ondelete='set null',
        index=True,
        help='Resolved partner — auto-created on first inbound from an '
             'unknown phone (mirrors P2 placeholder pattern).',
    )
    handler_user_id = fields.Many2one(
        'res.users',
        ondelete='set null',
        string='Handled by',
        help='Odoo user who handled the call. Resolved via htf.user.link '
             'from webhook.userId.',
    )
    hatif_user_name = fields.Char(
        string='Hatif User Name (raw)',
        help='Plain user display from Hatif — kept even when handler '
             'cannot be mapped to an Odoo user.',
    )
    ai_agent_uuid = fields.Char(
        string='AI Agent UUID',
        help='Hatif-side AI agent that handled the call. Null if a human '
             'agent handled it. Wired to numo_crm_htf bridge in P11.',
    )

    # Recording + analytics ------------------------------------------- #
    recording_url = fields.Char(
        help='URL to the call recording audio file. Treat as ephemeral '
             'per Q-06 ASSUMED — Hatif retention not documented. T4.9 '
             'cache option (deferred) copies into ir.attachment.',
    )
    transcription_text = fields.Text(
        help='Full transcript flattened from transcription.text. '
             'transcription.words[] preserved separately for click-to-seek.',
    )
    transcription_words_json = fields.Text(
        string='Transcription Words (JSON)',
        help='transcription.words[] as raw JSON: [{text,start,end,type,'
             'speaker}, ...]. Click-to-seek transcript widget parses this.',
    )
    summary = fields.Text(
        string='AI Summary',
        help='Hatif-generated summary of the call. Treat as authoritative '
             'for chatter previews; LLM re-analysis happens in P9.',
    )
    sentiment = fields.Selection(
        selection=[
            ('positive', 'Positive'),
            ('neutral', 'Neutral'),
            ('negative', 'Negative'),
            ('mixed', 'Mixed'),
            ('unknown', 'Unknown'),
        ],
        index=True,
    )
    evaluation_criteria_json = fields.Text(
        string='Evaluation Criteria (JSON)',
        help='Hatif-side QA rubric results: [{id,dataType,description,'
             'value,rationale}, ...]. Surfaced as a table in the call '
             'form view.',
    )

    # CSAT (customer satisfaction) — Hatif fields not in the apidog
    # spec but present on every live Call Webhook payload (verified
    # 2026-05-19 via raw_payload inspection on erp.amro.pro).
    csat_rating = fields.Integer(
        string='CSAT Rating',
        help='Customer satisfaction score from Hatif (when collected).',
    )
    csat_method = fields.Char(
        string='CSAT Method',
        help='How the rating was collected (e.g. IVR, post-call SMS).',
    )
    csat_collected_at = fields.Datetime(
        string='CSAT Collected At',
        help='When the rating was captured (may post-date the call).',
    )

    # Hatif now flags AI-handled calls so we can route + filter them
    # separately from human-handled ones (P11 / numo_crm_htf concern).
    is_ai_call = fields.Boolean(
        string='AI-Handled',
        default=False,
        index=True,
        help='Hatif flag — call was answered by an AI agent rather '
             'than a human. P11 bridge consumes this to route AI '
             'handoffs differently.',
    )

    # Derived classification (live-UAT 2026-05-19 finding): Hatif's
    # status=Missed semantic means 'no INTENDED human agent picked
    # up' — it can still co-exist with pickup_time + recording when
    # the auto-responder / IVR / AI / unmapped agent answered. This
    # field lets reports bucket cleanly: truly missed vs after-hours-
    # handled vs human-answered.
    pickup_kind = fields.Selection(
        selection=[
            ('human',  'Human agent'),
            ('system', 'System / bot / unmapped agent'),
            ('none',   'No pickup'),
        ],
        compute='_compute_pickup_kind',
        store=True,
        index=True,
        string='Pickup By',
        help='How the call was answered:\n'
             '  • Human agent — pickup_time AND handler_user_id set\n'
             '  • System — pickup_time set but no Odoo-mapped agent\n'
             '    (likely IVR / auto-responder / AI / unmapped human)\n'
             '  • No pickup — phone rang but nobody answered',
    )

    # Audit ----------------------------------------------------------- #
    chatter_message_id = fields.Many2one(
        'mail.message',
        ondelete='set null',
        copy=False,
        help='Back-ref to the chatter post on the resolved partner '
             '(or lead). Used by status updates to refresh in place.',
    )
    raw_payload = fields.Text(
        help='JSON-serialized webhook body (after PII redaction). Useful '
             'when transcription renders oddly or status transitions '
             'fail. Trim periodically.',
    )

    # Constraints ----------------------------------------------------- #
    # Plain UNIQUE — Postgres treats NULLs as distinct, so a brief
    # window where Hatif sends a webhook without a call id (rare) won't
    # collide on null.
    _htf_call_id_unique = models.Constraint(
        'unique(htf_call_id)',
        'Hatif call id must be unique when present.',
    )

    # Computes -------------------------------------------------------- #
    @api.depends('direction', 'status', 'partner_id.name', 'channel_id.display_name')
    def _compute_name(self):
        for rec in self:
            direction = (
                _('Inbound') if rec.direction == 'inbound' else _('Outbound')
            )
            status = dict(self._fields['status'].selection).get(
                rec.status or '', rec.status or '?'
            )
            who = rec.partner_id.name or _('Unknown')
            via = rec.channel_id.display_name or rec.channel_id.name or '—'
            rec.name = f"[{direction} {status}] {who} via {via}"

    @api.depends('pickup_time', 'handler_user_id')
    def _compute_pickup_kind(self):
        for rec in self:
            if not rec.pickup_time:
                rec.pickup_kind = 'none'
            elif rec.handler_user_id:
                rec.pickup_kind = 'human'
            else:
                rec.pickup_kind = 'system'

    @api.depends('duration_seconds')
    def _compute_duration_display(self):
        for rec in self:
            secs = max(int(rec.duration_seconds or 0), 0)
            m, s = divmod(secs, 60)
            h, m = divmod(m, 60)
            if h:
                rec.duration_display = f'{h}:{m:02d}:{s:02d}'
            else:
                rec.duration_display = f'{m}:{s:02d}'

    @api.depends('pickup_time', 'hangup_time', 'call_length_raw')
    def _compute_duration(self):
        for rec in self:
            if rec.pickup_time and rec.hangup_time:
                delta = rec.hangup_time - rec.pickup_time
                rec.duration_seconds = max(int(delta.total_seconds()), 0)
                continue
            # Fall back to parsing HH:MM:SS string from Hatif.
            raw = (rec.call_length_raw or '').strip()
            if not raw:
                rec.duration_seconds = 0
                continue
            try:
                parts = raw.split(':')
                if len(parts) == 3:
                    h, m, s = (int(x) for x in parts)
                    rec.duration_seconds = h * 3600 + m * 60 + s
                elif len(parts) == 2:
                    m, s = (int(x) for x in parts)
                    rec.duration_seconds = m * 60 + s
                else:
                    rec.duration_seconds = 0
            except (TypeError, ValueError):
                rec.duration_seconds = 0

    # API helpers ----------------------------------------------------- #
    @api.model
    def find_by_call_id(self, htf_call_id: str):
        """Return existing call by Hatif id, or empty recordset."""
        if not htf_call_id:
            return self.browse()
        return self.search([('htf_call_id', '=', htf_call_id)], limit=1)

    # Bucket helper for signal dispatch ------------------------------- #
    def signal_bucket(self) -> str:
        """Return the htf signal name appropriate to this call's status.

        - completed         → 'htf.call.received'
        - failed            → 'htf.call.failed'
        - missed family     → 'htf.call.missed'
        - active / unknown  → '' (no signal — call still in flight)
        """
        self.ensure_one()
        if self.status in COMPLETED_STATUSES:
            return 'htf.call.received'
        if self.status in FAILED_STATUSES:
            return 'htf.call.failed'
        if self.status in MISSED_STATUSES:
            return 'htf.call.missed'
        return ''
