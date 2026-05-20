"""htf.template — locally registered Hatif/Meta WhatsApp templates.

Why this model exists: the Send WhatsApp wizard previously asked the
agent to TYPE the exact template name (case-sensitive) into a free-form
``Char`` field. Typos / wrong case / wrong language tag / sending on
the wrong channel were the four most common causes of 400s from
Hatif — and we had no way to surface a "did you mean" list.

This model is the local mirror of an approved Hatif template:
- ``name`` — the exact Meta-side template id (e.g. ``welcom_message``,
  ``order_shipped_v2``). Case-sensitive.
- ``channel_id`` — which Hatif channel approved this template. Meta
  approves templates per WhatsApp Business number, so the same name
  on a different channel is a different template.
- ``language`` — ISO tag (``ar``, ``en``, ``ar_SA``) MUST match the
  approval on Hatif.
- ``category``, ``status``, ``body_preview``, ``parameter_count``,
  ``parameter_hint`` — admin metadata so the wizard can auto-fill the
  Send WA wizard once a template is picked.

The wizard's ``template_id`` Many2one targets this model, with a
domain that filters by the wizard's selected channel AND the current
user's allowed-channels override on ``htf.channel.user_ids``. The
free-form ``template_name`` field stays as a fallback for templates
not yet registered locally.
"""

from __future__ import annotations

from odoo import _, api, fields, models


class HtfTemplate(models.Model):
    _name = 'htf.template'
    _description = 'Hatif / Meta WhatsApp Template'
    _order = 'channel_id, name, language'
    _rec_name = 'name'

    name = fields.Char(
        string='Template Name',
        required=True,
        index=True,
        help='Exact CASE-SENSITIVE template name as approved on Hatif / '
             'Meta (e.g. ``welcom_message``, ``order_shipped_v2``). '
             'Must match byte-for-byte — Meta is strict.',
    )
    channel_id = fields.Many2one(
        'htf.channel',
        string='Hatif Channel',
        required=True,
        ondelete='cascade',
        domain="[('state', '=', 'active'),"
               " ('channel_type', 'in', ['whatsapp', 'both'])]",
        help='Hatif channel this template is approved on. Meta approves '
             'templates PER WhatsApp Business number, so the same name '
             'on a different channel is technically a different template.',
    )
    language = fields.Char(
        string='Language Tag',
        required=True,
        default='ar',
        help='ISO language tag (``ar``, ``en``, ``ar_SA``, ``en_US``) '
             'matching the approved language on Hatif. Must match '
             'byte-for-byte — ``ar`` and ``ar_SA`` are NOT interchangeable.',
    )
    category = fields.Selection(
        selection=[
            ('marketing', 'Marketing'),
            ('utility', 'Utility'),
            ('authentication', 'Authentication'),
            ('service', 'Service'),
        ],
        default='utility',
        required=True,
        help='Meta template category. Drives billing on the htf.message '
             '``meta_category`` field — `service` is free, others are paid.',
    )
    status = fields.Selection(
        selection=[
            ('approved', 'Approved (Active)'),
            ('pending', 'Under Review'),
            ('rejected', 'Rejected'),
            ('paused', 'Paused'),
            ('archived', 'Archived'),
        ],
        default='approved',
        required=True,
        index=True,
        help='Mirror of the Hatif portal status. Only ``Approved`` '
             'templates can actually send — the wizard hides everything '
             'else from the dropdown to prevent guaranteed 400s.',
    )
    active = fields.Boolean(default=True, index=True)
    body_preview = fields.Text(
        string='Body Preview',
        help='Copy of the template body for agent reference. Use '
             '``{{1}}``, ``{{2}}`` for body variables matching the Hatif '
             'side. Stored here ONLY for UI hints — the actual approved '
             'body lives on Hatif/Meta.',
    )
    parameter_count = fields.Integer(
        string='Body Parameters',
        default=0,
        help='How many body variables (``{{1}}``, ``{{2}}``, …) the '
             'template expects. The wizard uses this to validate the '
             '``Body Variables`` field before submitting.',
    )
    parameter_hint = fields.Char(
        string='Parameter Hint',
        help='Pipe-separated example values for the body variables '
             '(e.g. ``Ahmed|ORD-5123|confirmed``). Shown as the wizard '
             'placeholder when the agent selects this template.',
    )
    notes = fields.Text(
        help='Free-form admin notes — e.g. "Used for order confirmations" '
             'or "Cambridge campaign Q4".',
    )

    # Helpful display label for the wizard dropdown:
    #   "welcom_message  ·  ar  ·  Approved"
    display_name = fields.Char(
        compute='_compute_display_name', store=True,
    )

    _template_name_channel_lang_unique = models.Constraint(
        'unique(name, channel_id, language)',
        'A template with this name + language already exists on this '
        'channel. Update the existing row instead of creating a duplicate.',
    )

    @api.depends('name', 'language', 'status', 'channel_id.display_name')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.name or _('(unnamed)')]
            if rec.language:
                parts.append(rec.language)
            if rec.status and rec.status != 'approved':
                parts.append(dict(rec._fields['status'].selection).get(rec.status, rec.status))
            rec.display_name = '  ·  '.join(parts)
