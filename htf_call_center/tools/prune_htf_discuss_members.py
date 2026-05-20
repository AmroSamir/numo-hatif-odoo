"""Prune Hatif Discuss channel membership to authorised users only.

Reverses the UAT-stage bulk-invite that ``grant_htf_discuss_members.py``
performed (it added every internal user to every Hatif channel so the
team could eyeball P7 immediately). With that left in place, ANY
internal user can read EVERY customer's Hatif conversation — a real
privacy issue once the workspace has >1 sales agent.

For every channel with ``x_htf_partner_id`` set, this tool computes
the AUTHORISED member set:

  - the customer's partner (always, needed so author_id rendering on
    inbound bubbles attributes to the customer's name + avatar);
  - every user in ``htf_call_center.group_admin`` (Hatif admins see
    everything by design);
  - every user who is the ``salesperson`` (``user_id``) on a CRM lead
    or opportunity whose ``partner_id`` is the customer (the agents
    actually working that customer).

Members NOT in the authorised set are dropped from the channel via
``discuss.channel.member.unlink()``. Idempotent — re-runs find zero
extras and exit clean.

Env-var knobs (read from the wrapper shell script):

    HTF_DRY_RUN=1                  → preview, no writes
    HTF_CHANNEL_LIMIT=N            → process at most N channels
    HTF_CHANNEL_HINT=<id|name>     → scope to one channel

Run via the wrapper:
    bash htf_call_center/tools/prune_htf_discuss_members.sh
"""

import logging
import os

_logger = logging.getLogger(__name__)

DRY_RUN = bool(os.environ.get('HTF_DRY_RUN'))
CHANNEL_LIMIT = int(os.environ.get('HTF_CHANNEL_LIMIT') or '0') or None
CHANNEL_HINT = (os.environ.get('HTF_CHANNEL_HINT') or '').strip()


def _allowed_partner_ids(env, partner):
    """Return the set of res.partner ids that SHOULD be members of
    the Hatif channel for ``partner``.

    Delegates to the model so the prune CLI, the auto-provisioning
    code, the channel write hook, and the CRM-lead write hook all
    converge on the same 2-gate rule. Pre-19.0.1.27.0 this function
    inlined the logic; keeping the wrapper preserves the old CLI
    surface for anyone who scripted against it.
    """
    return env['discuss.channel'].sudo()._htf_allowed_member_partner_ids(partner)


def run(env):
    Channel = env['discuss.channel'].sudo()
    Member = env['discuss.channel.member'].sudo()

    domain = [('x_htf_partner_id', '!=', False), ('active', '=', True)]
    if CHANNEL_HINT:
        if CHANNEL_HINT.isdigit():
            domain.append(('id', '=', int(CHANNEL_HINT)))
        else:
            domain.append(('name', 'ilike', CHANNEL_HINT))
    channels = Channel.search(domain, limit=CHANNEL_LIMIT)

    print(f'scanning {len(channels)} Hatif channel(s)...')

    total_kept = 0
    total_removed = 0
    for ch in channels:
        partner = ch.x_htf_partner_id
        allowed = _allowed_partner_ids(env, partner)
        members = ch.channel_member_ids
        to_remove = members.filtered(lambda m: m.partner_id.id not in allowed)
        to_keep = members - to_remove

        kept_names = ', '.join(sorted(
            ((m.partner_id.name or '?')[:24] for m in to_keep)
        )[:6])
        if len(to_keep) > 6:
            kept_names += ', …'

        if to_remove:
            print(f'  ch id={ch.id} name={ch.name[:30]!r} '
                  f'remove {len(to_remove)} / keep {len(to_keep)} '
                  f'(kept: {kept_names})')
            if DRY_RUN:
                for m in to_remove[:5]:
                    print(f'    [DRY-RUN] would remove partner '
                          f'id={m.partner_id.id} name={(m.partner_id.name or "?")[:30]!r}')
                if len(to_remove) > 5:
                    print(f'    [DRY-RUN] ...and {len(to_remove) - 5} more')
            else:
                try:
                    to_remove.unlink()
                except Exception:  # noqa: BLE001
                    _logger.exception(
                        "[htf-prune] failed unlinking members of channel id=%s",
                        ch.id,
                    )
                total_removed += len(to_remove)
        total_kept += len(to_keep)

    if DRY_RUN:
        print('[DRY-RUN] no writes performed.')
    else:
        env.cr.commit()
        print(f'done — kept {total_kept} member(s), removed {total_removed} '
              f'unauthorised member(s) across {len(channels)} channel(s).')


try:
    _env = self.env  # type: ignore[name-defined]  # noqa: F821
except NameError:  # pragma: no cover
    _env = None

if _env is None:
    print('ERROR: this script must be run inside `odoo shell`.')
else:
    run(_env)
