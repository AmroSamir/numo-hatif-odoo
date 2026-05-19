"""P7 SAFE-REVERT companion — re-enable after a Tier 3 rollback.

Reverses the action of ``disable_p7_discuss.py``:

1. Flips all 5 ``ir.config_parameter`` feature flags back to ``True``:
   * ``htf_call_center.discuss_mirror_enabled``
   * ``htf_call_center.discuss_mirror_inbound``
   * ``htf_call_center.discuss_mirror_calls``
   * ``htf_call_center.discuss_outbound_route``
   * ``htf_call_center.discuss_ui_override``
2. Un-archives every ``discuss.channel`` where ``x_htf_partner_id IS NOT NULL``
   (sets ``active=True``).

Properties:

* **Idempotent** — second run is a no-op (flags already on, channels
  already active).
* **Symmetric with** ``disable_p7_discuss.py`` — same channel set is
  toggled.
* **Granular re-enable**: if you want to re-enable only the master
  flag and keep sub-features off, edit the FLAGS list below or just
  use the Odoo UI / shell directly. This script is the blunt-force
  "turn the whole thing back on" tool.

Usage::

    python3 enable_p7_discuss.py <db>
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
    return line.split(':', 1)[1].strip() if line.startswith(prefix) else ''


def enable_flags(db: str) -> dict[str, str]:
    log(f'PLAN: set {len(FLAGS)} ir.config_parameter rows to True on db={db!r}')
    for f in FLAGS:
        log(f'  - {f} -> True')
    py_flags = '[' + ', '.join(repr(f) for f in FLAGS) + ']'
    script = f"""
ICP = env['ir.config_parameter'].sudo()
prev = {{}}
for key in {py_flags}:
    prev[key] = ICP.get_param(key, default='')
    ICP.set_param(key, 'True')
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
        raise RuntimeError(f'flag enable did not complete:\n{out}')
    for k in FLAGS:
        log(f'  flag {k} was {prev.get(k, "<unset>")!r} -> now True')
    return prev


def unarchive_mirrored_channels(db: str) -> tuple[int, int]:
    """Un-archive every ``discuss.channel`` with ``x_htf_partner_id`` set.

    Returns ``(partner_count, channel_count)``.
    """
    log('PLAN: unarchive every discuss.channel where x_htf_partner_id IS NOT NULL')
    script = """
Ch = env['discuss.channel'].sudo()
all_mirrored = Ch.with_context(active_test=False).search(
    [('x_htf_partner_id', '!=', False)],
)
archived = all_mirrored.filtered(lambda c: not c.active)
partner_ids = set(all_mirrored.mapped('x_htf_partner_id.id'))
print('PARTNER_COUNT:' + str(len(partner_ids)))
print('TOTAL_CHANNELS:' + str(len(all_mirrored)))
print('ARCHIVED_BEFORE:' + str(len(archived)))
if archived:
    archived.write({'active': True})
    env.cr.commit()
print('UNARCHIVED_NOW:' + str(len(archived)))
print('DONE_UNARCHIVE')
"""
    out = shell(db, script)
    if 'DONE_UNARCHIVE' not in out:
        raise RuntimeError(f'unarchive did not complete:\n{out}')
    p_count = c_total = c_arch = 0
    for line in out.splitlines():
        if line.startswith('PARTNER_COUNT:'):
            p_count = int(_parse_pair(line, 'PARTNER_COUNT:') or '0')
        elif line.startswith('TOTAL_CHANNELS:'):
            c_total = int(_parse_pair(line, 'TOTAL_CHANNELS:') or '0')
        elif line.startswith('ARCHIVED_BEFORE:'):
            c_arch = int(_parse_pair(line, 'ARCHIVED_BEFORE:') or '0')
    log(f'  partners with mirrored channels    : {p_count}')
    log(f'  mirrored channels total            : {c_total}')
    log(f'  mirrored channels unarchived now   : {c_arch}')
    log(f'  mirrored channels already active   : {c_total - c_arch}')
    return p_count, c_total


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        print('ERROR: expected exactly one arg (database name).', file=sys.stderr)
        return 2
    db = argv[1]
    log(f'=== P7 ENABLE (reverse of Tier 3) — db={db!r} ===')
    enable_flags(db)
    partners, channels = unarchive_mirrored_channels(db)
    log('=== DONE ===')
    log(f'Summary: 5 flags True, {channels} mirrored channels active '
        f'(covering {partners} partners).')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
