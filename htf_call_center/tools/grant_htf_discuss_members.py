"""Grant every active internal Odoo user membership of every Hatif Discuss channel.

Workaround for: the per-partner Discuss channel auto-provisioned by
P7 adds only the customer (partner) as a member. Internal users are
not added automatically, so the channels are invisible in their
Discuss sidebars.

This script bulk-adds every internal user as a member of every
Hatif-linked channel (where ``x_htf_partner_id IS NOT NULL``).
Idempotent — re-running creates no duplicates.

Long-term, P8 will introduce per-customer agent routing (only the
agents who handle a given customer become members). This script is
the UAT-stage shortcut so the whole team can eyeball P7 immediately.

Usage:
    python3 grant_htf_discuss_members.py <db>

Container override (e.g., on erp.amro.pro):
    HTF_CONTAINER=web-erp-amro-pro python3 grant_htf_discuss_members.py numo
"""

from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys


CONTAINER = os.environ.get('HTF_CONTAINER', 'odoo-app')


def log(msg: str) -> None:
    ts = _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


_SCRIPT = r"""
chs = env['discuss.channel'].sudo().search([('x_htf_partner_id', '!=', False)])
users = env['res.users'].sudo().search([('share', '=', False), ('active', '=', True)])
Mem = env['discuss.channel.member'].sudo()
added = 0
errors = 0
for ch in chs:
    existing = {m.partner_id.id for m in ch.channel_member_ids}
    for u in users:
        if u.partner_id.id in existing:
            continue
        try:
            Mem.create({'channel_id': ch.id, 'partner_id': u.partner_id.id})
            added += 1
        except Exception:
            errors += 1
env.cr.commit()
print(f'CHANNELS:{len(chs)}')
print(f'USERS:{len(users)}')
print(f'ADDED:{added}')
print(f'ERRORS:{errors}')
"""


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        print('ERROR: expected exactly one arg (database name).', file=sys.stderr)
        return 2
    db = argv[1]
    log(f'=== GRANT P7 MEMBERSHIPS — db={db!r} container={CONTAINER!r} ===')
    log('PLAN: add every active internal user as a member of every Hatif-linked channel')
    proc = subprocess.run(
        ['docker', 'exec', '-i', CONTAINER, 'odoo', 'shell',
         '-d', db, '--no-http', '--log-level=error'],
        input=_SCRIPT.encode(), capture_output=True, timeout=180,
    )
    out = proc.stdout.decode('utf-8', errors='replace')
    err = proc.stderr.decode('utf-8', errors='replace')
    if proc.returncode != 0:
        sys.stderr.write(err)
        log(f'FAILED (returncode={proc.returncode})')
        return 1

    def _int(label: str) -> int:
        for line in out.splitlines():
            if line.startswith(label):
                try:
                    return int(line.split(':', 1)[1])
                except ValueError:
                    return 0
        return 0

    channels = _int('CHANNELS:')
    users = _int('USERS:')
    added = _int('ADDED:')
    errors = _int('ERRORS:')
    log(f'  Hatif-linked channels : {channels}')
    log(f'  internal users        : {users}')
    log(f'  memberships added now : {added}')
    log(f'  errors                : {errors}')
    log('=== DONE ===')
    if added == 0 and channels > 0:
        log('No new memberships — every user was already a member of every channel.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
