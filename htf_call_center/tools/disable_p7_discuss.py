"""P7 SAFE-REVERT — Tier 3 escalation.

Disable the entire P7 "mirror Hatif calls + WhatsApp into per-partner
Odoo Discuss channels" feature in one shot.

What this does:

1. Flips all 5 ``ir.config_parameter`` feature flags to ``False``:
   * ``htf_call_center.discuss_mirror_enabled`` (master kill-switch)
   * ``htf_call_center.discuss_mirror_inbound``
   * ``htf_call_center.discuss_mirror_calls``
   * ``htf_call_center.discuss_outbound_route``
   * ``htf_call_center.discuss_ui_override``
2. Archives every ``discuss.channel`` linked to a Hatif partner —
   i.e. ``x_htf_partner_id IS NOT NULL`` — by setting ``active=False``.
   The rows + their messages stay in the DB so we can reverse.
3. Prints a count of partners + channels touched.

Properties:

* **Idempotent** — second run is a no-op (flags already off, channels
  already archived).
* **Reversible** — ``enable_p7_discuss.py`` flips everything back on
  and un-archives the same channels.
* **Non-destructive** — no rows are deleted. For destructive rollback
  see ``unbackfill_htf_discuss.py``.

Usage::

    python3 disable_p7_discuss.py <db>
    # e.g.
    python3 disable_p7_discuss.py odoo

The script shells out to ``docker exec -i odoo-app odoo shell -d <db>``
just like ``htf_p4_check.py``. It does NOT import any Odoo modules
directly from the host.
"""

from __future__ import annotations

import datetime as _dt
import subprocess
import sys


CONTAINER = 'odoo-app'

FLAGS = (
    'htf_call_center.discuss_mirror_enabled',
    'htf_call_center.discuss_mirror_inbound',
    'htf_call_center.discuss_mirror_calls',
    'htf_call_center.discuss_outbound_route',
    'htf_call_center.discuss_ui_override',
)


def _ts() -> str:
    return _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(msg: str) -> None:
    print(f'[{_ts()}] {msg}', flush=True)


def shell(db: str, script: str, timeout: int = 120) -> str:
    """Execute a Python snippet inside ``odoo shell`` on ``db``."""
    p = subprocess.run(
        ['docker', 'exec', '-i', CONTAINER, 'odoo', 'shell',
         '-d', db, '--no-http', '--log-level=warn'],
        input=script.encode(), capture_output=True, timeout=timeout,
    )
    out = p.stdout.decode('utf-8', errors='replace')
    err = p.stderr.decode('utf-8', errors='replace')
    if p.returncode != 0:
        raise RuntimeError(
            f'odoo shell exited {p.returncode}\nSTDOUT:\n{out}\nSTDERR:\n{err}'
        )
    return out


def _parse_pair(line: str, prefix: str) -> str:
    """Pull the value off a ``PREFIX:value`` print line."""
    return line.split(':', 1)[1].strip() if line.startswith(prefix) else ''


def disable_flags(db: str) -> dict[str, str]:
    """Set every P7 feature flag to ``False``.

    Returns a dict ``{flag_key: previous_value}`` for the audit log.
    """
    log(f'PLAN: set {len(FLAGS)} ir.config_parameter rows to False on db={db!r}')
    for f in FLAGS:
        log(f'  - {f} -> False')

    py_flags = '[' + ', '.join(repr(f) for f in FLAGS) + ']'
    script = f"""
ICP = env['ir.config_parameter'].sudo()
prev = {{}}
for key in {py_flags}:
    prev[key] = ICP.get_param(key, default='')
    ICP.set_param(key, 'False')
env.cr.commit()
for k, v in prev.items():
    print('PREV:' + k + '=' + (v or ''))
print('DONE_FLAGS')
"""
    out = shell(db, script)
    prev: dict[str, str] = {}
    for line in out.splitlines():
        if line.startswith('PREV:'):
            body = line[len('PREV:'):]
            if '=' in body:
                k, v = body.split('=', 1)
                prev[k] = v
    if 'DONE_FLAGS' not in out:
        raise RuntimeError(f'flag disable did not complete:\n{out}')
    for k in FLAGS:
        log(f'  flag {k} was {prev.get(k, "<unset>")!r} -> now False')
    return prev


def archive_mirrored_channels(db: str) -> tuple[int, int]:
    """Archive every ``discuss.channel`` with ``x_htf_partner_id`` set.

    Returns ``(partner_count, channel_count)``.
    """
    log('PLAN: archive every discuss.channel where x_htf_partner_id IS NOT NULL')
    script = """
Ch = env['discuss.channel'].sudo()
# active_test=False so we see already-archived rows too — keeps the
# operation idempotent (we just no-op on rows already inactive).
all_mirrored = Ch.with_context(active_test=False).search(
    [('x_htf_partner_id', '!=', False)],
)
live = all_mirrored.filtered(lambda c: c.active)
partner_ids = set(all_mirrored.mapped('x_htf_partner_id.id'))
print('PARTNER_COUNT:' + str(len(partner_ids)))
print('TOTAL_CHANNELS:' + str(len(all_mirrored)))
print('LIVE_CHANNELS:' + str(len(live)))
if live:
    live.write({'active': False})
    env.cr.commit()
print('ARCHIVED_NOW:' + str(len(live)))
print('DONE_ARCHIVE')
"""
    out = shell(db, script)
    if 'DONE_ARCHIVE' not in out:
        raise RuntimeError(f'archive did not complete:\n{out}')
    p_count = c_total = c_live = 0
    for line in out.splitlines():
        if line.startswith('PARTNER_COUNT:'):
            p_count = int(_parse_pair(line, 'PARTNER_COUNT:') or '0')
        elif line.startswith('TOTAL_CHANNELS:'):
            c_total = int(_parse_pair(line, 'TOTAL_CHANNELS:') or '0')
        elif line.startswith('LIVE_CHANNELS:'):
            c_live = int(_parse_pair(line, 'LIVE_CHANNELS:') or '0')
    log(f'  partners with mirrored channels: {p_count}')
    log(f'  mirrored channels total       : {c_total}')
    log(f'  mirrored channels archived now: {c_live}')
    log(f'  mirrored channels already off : {c_total - c_live}')
    return p_count, c_total


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        print('ERROR: expected exactly one arg (database name).', file=sys.stderr)
        return 2
    db = argv[1]
    log(f'=== P7 DISABLE (Tier 3 revert) — db={db!r} ===')
    log('This run is idempotent and reversible via enable_p7_discuss.py.')
    disable_flags(db)
    partners, channels = archive_mirrored_channels(db)
    log('=== DONE ===')
    log(f'Summary: 5 flags False, {channels} mirrored channels archived '
        f'(covering {partners} partners).')
    log('Reverse with: python3 enable_p7_discuss.py ' + db)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
