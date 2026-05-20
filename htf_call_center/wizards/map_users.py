"""Map Users wizard — match Hatif workspace users to Odoo res.users.

Steps:
  1. Click "Sync from Hatif" → service pulls workspace users into
     htf.user.link rows.
  2. Auto-match suggestions populate as wizard lines. Two-stage:
       (a) Email — login, partner.email, partner.email_normalized
           (case-insensitive)
       (b) Fuzzy name — Arabic-normalized token containment when
           email match fails. e.g. Hatif 'شموس عبدالكريم' matches
           Odoo 'شموس عبدالكريم السليمان'.
  3. Each line ALSO lets the admin pick which Hatif channels the
     mapped user is allowed to send through. Pre-filled from the
     existing ``htf.channel.user_ids`` overrides; saving the wizard
     diffs additions / removals and writes them back per channel.
  4. Admin reviews + overrides per row. Click 'Re-suggest unmapped'
     to retry just the empty rows (preserves manual overrides).
  5. Apply → writes user_id on each link AND res.users.x_htf_user_id /
     x_htf_user_email / x_htf_role on the matching Odoo user; syncs
     the user's channel membership on every selected channel.

Idempotent — re-running keeps already-mapped rows and only fills empties.
"""

from __future__ import annotations

import re
import unicodedata

from odoo import _, api, fields, models


# ---------------------------------------------------------------- #
# Fuzzy-name match helpers                                         #
# ---------------------------------------------------------------- #

_ARABIC_ALEF_NORM = str.maketrans({
    'أ': 'ا', 'إ': 'ا', 'آ': 'ا',  # alef variants
    'ى': 'ي',                       # alef maksura → ya
    'ة': 'ه',                       # ta marbuta → ha
})


def _normalize_name(text: str) -> str:
    """Lowercase + strip diacritics + normalize Arabic letter shapes.

    Lets 'شموس عبدالكريم' match 'شموس عبدالكريم السليمان' (Hatif name
    is a prefix of the Odoo name) and also handles minor spelling
    variants in Saudi names (alef hamza, ta marbuta, etc.).
    """
    if not text:
        return ''
    # Unicode decompose + drop combining marks (Arabic diacritics).
    norm = unicodedata.normalize('NFKD', text)
    norm = ''.join(c for c in norm if unicodedata.category(c) != 'Mn')
    norm = norm.translate(_ARABIC_ALEF_NORM)
    norm = norm.lower().strip()
    # Collapse whitespace + strip punctuation that isn't a word char.
    norm = re.sub(r'[^\w\s]', ' ', norm, flags=re.UNICODE)
    norm = re.sub(r'\s+', ' ', norm)
    return norm


def _tokenize_name(text: str) -> list[str]:
    n = _normalize_name(text)
    return [t for t in n.split(' ') if t]


def _suggest_user(env, link):
    """Return res.users best-match for a htf.user.link, or empty rs.

    Order: email-on-login → email-on-partner-email → fuzzy name match.
    """
    ResUsers = env['res.users']
    email = (link.email or '').strip()

    if email:
        # Email-on-login.
        u = ResUsers.search([('login', '=ilike', email)], limit=1)
        if u:
            return u
        # Email-on-partner.email — most enterprise installs put the
        # real email here while login is a short username.
        u = ResUsers.search([('partner_id.email', '=ilike', email)], limit=1)
        if u:
            return u

    # Fuzzy name match. Tokenise the Hatif display name + try to find
    # an active Odoo user whose name contains ALL the Hatif tokens.
    raw = (link.display_name or '').strip()
    tokens = _tokenize_name(raw)
    if not tokens:
        return ResUsers.browse()

    # Pull a reasonable pool of candidate users + filter in Python so
    # we get diacritic-normalised matching the ORM domain can't do.
    candidates = ResUsers.search(
        [('active', '=', True), ('share', '=', False)], limit=300,
    )
    best = ResUsers.browse()
    best_token_count = 0
    for u in candidates:
        u_tokens = _tokenize_name(u.name or '')
        if not u_tokens:
            continue
        matched = sum(1 for t in tokens if t in u_tokens)
        if matched == len(tokens):
            # Full coverage of Hatif tokens — likely correct.
            return u
        if matched >= 2 and matched > best_token_count:
            # Partial 2+ token match — keep as best fallback.
            best = u
            best_token_count = matched
    return best


class HtfMapUsersWizard(models.TransientModel):
    _name = 'htf.map.users.wizard'
    _description = 'Map Hatif Users to Odoo Users'

    line_ids = fields.One2many('htf.map.users.wizard.line', 'wizard_id')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        Link = self.env['htf.user.link']
        # Order by STORED fields only — `display_name` is computed and
        # raises "Cannot convert to SQL" if used here.
        unmapped = Link.search([
            ('is_ai_agent', '=', False),
        ], order='user_id, email, htf_user_id')

        Channel = self.env['htf.channel'].sudo()
        lines = []
        for link in unmapped:
            suggested = link.user_id  # preserve existing mapping
            if not suggested:
                suggested = _suggest_user(link.env, link)
            # Pre-fill channel membership from current overrides on
            # htf.channel.user_ids so the admin sees what's already
            # set and can extend or trim from there.
            current_channels = (
                Channel.search([
                    ('user_ids', 'in', suggested.id),
                    ('state', '=', 'active'),
                ])
                if suggested else Channel.browse()
            )
            lines.append((0, 0, {
                'link_id': link.id,
                'user_id': suggested.id if suggested else False,
                'channel_ids': [(6, 0, current_channels.ids)],
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

    def action_resuggest(self):
        """Re-run the auto-matcher on rows where user_id is still empty.

        Preserves any rows the admin already filled in manually. Useful
        after creating new Odoo users — click and pre-fill the gaps.
        """
        self.ensure_one()
        filled = 0
        for line in self.line_ids:
            if line.user_id:
                continue
            suggested = _suggest_user(self.env, line.link_id)
            if suggested:
                line.user_id = suggested.id
                filled += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Re-suggest done'),
                'message': _('%s row(s) auto-filled. Empty rows have '
                             'no match — pick manually or create '
                             'a matching Odoo user first.') % filled,
                'sticky': False,
            },
        }

    def action_apply(self):
        self.ensure_one()
        Channel = self.env['htf.channel'].sudo()
        channels_changed = 0
        touched_users = self.env['res.users']
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
                # Sync channel memberships: minimal diff between the
                # user's CURRENT set of active-channel overrides and
                # what the admin picked in the wizard. We write per
                # channel (add/remove ONE user) instead of replacing
                # channel.user_ids wholesale, so we don't clobber
                # OTHER users that happen to be on the same channel.
                current = Channel.search([
                    ('user_ids', 'in', user.id),
                    ('state', '=', 'active'),
                ])
                desired = line.channel_ids
                for ch in (desired - current):
                    ch.write({'user_ids': [(4, user.id)]})
                    channels_changed += 1
                for ch in (current - desired):
                    ch.write({'user_ids': [(3, user.id)]})
                    channels_changed += 1
                touched_users |= user
        # The channel write() hook already syncs group + discuss
        # membership for the diffed users, but also touch every user
        # we saw on a line so a no-op apply (admin opened the wizard,
        # picked nothing, hit Save) still converges the group state
        # in case it drifted (e.g. wizard ran from an older install
        # before group autosync existed).
        if touched_users:
            touched_users._htf_sync_group_membership()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Mapping saved'),
                'message': _(
                    '%(links)s links updated, %(channels)s channel '
                    'membership change(s) applied.'
                ) % {
                    'links': len(self.line_ids),
                    'channels': channels_changed,
                },
                'sticky': False,
            },
        }


class HtfMapUsersWizardLine(models.TransientModel):
    _name = 'htf.map.users.wizard.line'
    _description = 'Map Hatif Users — line'

    wizard_id = fields.Many2one('htf.map.users.wizard', required=True, ondelete='cascade')
    # Must NOT be readonly at the model level — OWL drops readonly fields from
    # the form-save payload, so a default_get-supplied value gets stripped on
    # the round-trip and the required-field constraint then fires.
    # The view hides the column (column_invisible="1") so users still can't
    # edit it from the UI.
    link_id = fields.Many2one('htf.user.link', required=True)
    display_name = fields.Char(related='link_id.display_name', readonly=True)
    email = fields.Char(related='link_id.email', readonly=True)
    htf_user_id = fields.Char(related='link_id.htf_user_id', readonly=True)
    role = fields.Selection(related='link_id.role', readonly=True)
    user_id = fields.Many2one(
        'res.users',
        string='Odoo User',
        domain="[('active', '=', True)]",
    )
    channel_ids = fields.Many2many(
        'htf.channel',
        string='Allowed Hatif Channels',
        domain="[('state', '=', 'active')]",
        help='Hatif channels this user is allowed to send / call through. '
             'Pre-filled from htf.channel.user_ids; saving the wizard '
             'diffs additions and removals back onto each channel. '
             'Empty = the user inherits the team\'s default channel pool.',
    )
