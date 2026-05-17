"""Map Users wizard — match Hatif workspace users to Odoo res.users.

Steps:
  1. Click "Sync from Hatif" → service pulls workspace users into
     htf.user.link rows.
  2. Auto-match suggestions populate as wizard lines (case-insensitive
     email match against res.users.login).
  3. Admin reviews + overrides per row.
  4. Apply → writes user_id on each link AND res.users.x_htf_user_id /
     x_htf_user_email / x_htf_role on the matching Odoo user.

Idempotent — re-running clears suggestions and refreshes from the
latest htf.user.link state.
"""

from __future__ import annotations

from odoo import _, api, fields, models


class HtfMapUsersWizard(models.TransientModel):
    _name = 'htf.map.users.wizard'
    _description = 'Map Hatif Users to Odoo Users'

    line_ids = fields.One2many('htf.map.users.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        Link = self.env['htf.user.link']
        ResUsers = self.env['res.users']
        # Order by STORED fields only — `display_name` is computed and
        # raises "Cannot convert to SQL" if used here.
        unmapped = Link.search([
            ('is_ai_agent', '=', False),
        ], order='user_id, email, htf_user_id')

        lines = []
        for link in unmapped:
            suggested = link.user_id
            if not suggested and link.email:
                suggested = ResUsers.search([('login', '=ilike', link.email)], limit=1)
            lines.append((0, 0, {
                'link_id': link.id,
                'user_id': suggested.id if suggested else False,
            }))
        vals['line_ids'] = lines
        return vals

    def action_sync_from_hatif(self):
        self.env['htf.config'].get_service('workspace').sync_users()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_apply(self):
        self.ensure_one()
        for line in self.line_ids:
            link = line.link_id
            user = line.user_id
            link.write({'user_id': user.id if user else False})
            if user:
                user.write({
                    'x_htf_user_id': link.htf_user_id,
                    'x_htf_user_email': link.email or False,
                    'x_htf_role': link.role,
                })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Mapping saved'),
                'message': _('%s links updated.') % len(self.line_ids),
                'sticky': False,
            },
        }


class HtfMapUsersWizardLine(models.TransientModel):
    _name = 'htf.map.users.wizard.line'
    _description = 'Map Hatif Users — line'

    wizard_id = fields.Many2one('htf.map.users.wizard', required=True, ondelete='cascade')
    link_id = fields.Many2one('htf.user.link', required=True, readonly=True)
    display_name = fields.Char(related='link_id.display_name', readonly=True)
    email = fields.Char(related='link_id.email', readonly=True)
    htf_user_id = fields.Char(related='link_id.htf_user_id', readonly=True)
    role = fields.Selection(related='link_id.role', readonly=True)
    user_id = fields.Many2one(
        'res.users',
        string='Odoo User',
        domain="[('active', '=', True)]",
    )
