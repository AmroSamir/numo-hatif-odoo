"""P7 SAFE-REVERT — Tier 5 (heavy / destructive) rollback.

Removes every Hatif-mirrored ``mail.message`` row from the database
and archives the parent ``discuss.channel`` rows.

Use this ONLY when:

* You've already toggled the feature flags off (Tier 1/2/3) and
* You need to wipe the mirrored rows because they're confusing users
  or corrupting reports, AND
* You've accepted that the mirrored Discuss history will be lost.

What is touched:

* ``mail.message`` rows tagged as Hatif-mirrored. We use a wide net —
  rows match if ANY of the following is true:
    - ``subtype_id`` resolves to xmlid ``htf_call_center.mt_htf_mirror``
    - ``author_id`` is the ``htf_bot`` user's partner (lookup by
      xmlid ``htf_call_center.user_htf_bot`` if it exists, else by
      login ``htf_bot``)
    - ``res_model == 'discuss.channel'`` AND the channel has
      ``x_htf_partner_id`` set (defensive — covers messages posted to
      a mirrored channel even if the subtype/author tag is missing)
* ``discuss.channel`` rows with ``x_htf_partner_id IS NOT NULL`` —
  these get ARCHIVED (active=False), NOT deleted.

What is NOT touched:

* The original chatter rows on ``res.partner`` — the real call /
  WhatsApp history mirrored FROM. Untouched.
* The Hatif tables (``htf.call``, ``htf.wa.message``, etc.) — untouched.
* ``res.partner`` rows — untouched.
* The 5 feature flags — run ``disable_p7_discuss.py`` first if you
  haven't.

Safety rails:

* **--dry-run is the default.** No mutation without ``--commit``.
* Prints a per-criterion breakdown of what would be deleted BEFORE
  doing anything.
* Logs every mutation with a timestamp.

Usage::

    # See what would happen (safe):
    python3 unbackfill_htf_discuss.py <db>
    python3 unbackfill_htf_discuss.py <db> --dry-run

    # Actually do it (destructive):
    python3 unbackfill_htf_discuss.py <db> --commit

A future restore from PG backup is your only recovery path for the
mail.message rows — that's the trade-off Tier 5 is for.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import subprocess
import sys


import os

# Default container name is the local-dev `odoo-app`. Override with
# `HTF_CONTAINER=web-erp-amro-pro python3 unbackfill_htf_discuss.py numo`
# on environments where the Odoo container has a different name.
CONTAINER = os.environ.get('HTF_CONTAINER', 'odoo-app')


def _ts() -> str:
    return _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(msg: str) -> None:
    print(f'[{_ts()}] {msg}', flush=True)


def shell(db: str, script: str, timeout: int = 180) -> str:
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


def _parse_int(out: str, prefix: str) -> int:
    for line in out.splitlines():
        if line.startswith(prefix):
            try:
                return int(line.split(':', 1)[1].strip())
            except (IndexError, ValueError):
                return 0
    return 0


# -------------------------------------------------------------- #
# Snippet shared by both dry-run and commit paths.               #
#                                                                #
# Builds the candidate message-id set using the three criteria   #
# above and prints the breakdown.                                #
# -------------------------------------------------------------- #

_BUILD_CANDIDATES = """
Msg = env['mail.message'].sudo()
Ch  = env['discuss.channel'].sudo()
Subt = env['mail.message.subtype'].sudo()
User = env['res.users'].sudo()

# (1) subtype tag
subtype_ids = []
try:
    sub = env.ref('htf_call_center.mt_htf_mirror', raise_if_not_found=False)
    if sub:
        subtype_ids.append(sub.id)
except Exception:
    pass
print('SUBTYPE_FOUND:' + ('1' if subtype_ids else '0'))

# (2) deterministic message_id sentinel — every mirror write tagged
#     with <htf-msg-N@htf_call_center> or <htf-call-N@htf_call_center>
#     by services/discuss_mirror.py since P7.6. The message_id is a
#     stable string column with btree index in Odoo 19 so the LIKE
#     scan is bounded; we further restrict it by the same prefix
#     pattern services/discuss_mirror.py emits.
msg_id_pattern = '<htf-%@htf_call_center>'
ids_by_message_id = set(Msg.search([('message_id', '=like', msg_id_pattern)]).ids)
print('IDS_BY_MESSAGE_ID:' + str(len(ids_by_message_id)))

# (3) message posted to a mirrored discuss.channel
mirrored_channels = Ch.with_context(active_test=False).search(
    [('x_htf_partner_id', '!=', False)],
)
print('MIRRORED_CHANNEL_COUNT:' + str(len(mirrored_channels)))

ids_by_subtype = set()
if subtype_ids:
    ids_by_subtype = set(Msg.search([('subtype_id', 'in', subtype_ids)]).ids)
print('IDS_BY_SUBTYPE:' + str(len(ids_by_subtype)))


ids_by_channel = set()
if mirrored_channels:
    ids_by_channel = set(Msg.search([
        ('model', '=', 'discuss.channel'),
        ('res_id', 'in', mirrored_channels.ids),
    ]).ids)
print('IDS_BY_CHANNEL:' + str(len(ids_by_channel)))

all_ids = ids_by_subtype | ids_by_message_id | ids_by_channel
print('TOTAL_CANDIDATES:' + str(len(all_ids)))

# Belt-and-braces: never touch chatter rows attached to res.partner
# (those are the *original* history we mirror FROM and must preserve).
partner_chatter = set(Msg.search([
    ('id', 'in', list(all_ids)),
    ('model', '=', 'res.partner'),
]).ids)
print('PARTNER_CHATTER_PROTECTED:' + str(len(partner_chatter)))

safe_ids = sorted(all_ids - partner_chatter)
print('SAFE_TO_DELETE:' + str(len(safe_ids)))
"""


def survey(db: str) -> dict[str, int]:
    log('PLAN: surveying candidate mirrored mail.message rows...')
    out = shell(db, _BUILD_CANDIDATES + "\nprint('DONE_SURVEY')\n")
    if 'DONE_SURVEY' not in out:
        raise RuntimeError(f'survey did not complete:\n{out}')
    stats = {
        'subtype_found': _parse_int(out, 'SUBTYPE_FOUND:'),
        'mirrored_channels': _parse_int(out, 'MIRRORED_CHANNEL_COUNT:'),
        'by_subtype': _parse_int(out, 'IDS_BY_SUBTYPE:'),
        'by_message_id': _parse_int(out, 'IDS_BY_MESSAGE_ID:'),
        'by_channel': _parse_int(out, 'IDS_BY_CHANNEL:'),
        'total': _parse_int(out, 'TOTAL_CANDIDATES:'),
        'protected_chatter': _parse_int(out, 'PARTNER_CHATTER_PROTECTED:'),
        'safe_to_delete': _parse_int(out, 'SAFE_TO_DELETE:'),
    }
    log(f'  subtype xmlid resolved        : {bool(stats["subtype_found"])}')
    log(f'  mirrored channels             : {stats["mirrored_channels"]}')
    log(f'  msgs matched by subtype       : {stats["by_subtype"]}')
    log(f'  msgs matched by message_id    : {stats["by_message_id"]}')
    log(f'  msgs matched by channel       : {stats["by_channel"]}')
    log(f'  total unique candidates       : {stats["total"]}')
    log(f'  res.partner chatter kept      : {stats["protected_chatter"]} (NEVER deleted)')
    log(f'  safe to delete                : {stats["safe_to_delete"]}')
    return stats


def commit_delete(db: str) -> tuple[int, int]:
    """Actually delete the candidate messages and archive channels.

    Returns ``(deleted_messages, archived_channels)``.
    """
    log('PLAN: committing destructive delete + channel archive.')
    script = _BUILD_CANDIDATES + """
# Delete in chunks to avoid one giant transaction lock.
deleted = 0
CHUNK = 500
remaining = list(safe_ids)
while remaining:
    batch, remaining = remaining[:CHUNK], remaining[CHUNK:]
    Msg.browse(batch).unlink()
    deleted += len(batch)
    env.cr.commit()
print('DELETED:' + str(deleted))

# Archive every mirrored channel (live or already archived — idempotent).
live = mirrored_channels.filtered(lambda c: c.active)
if live:
    live.write({'active': False})
    env.cr.commit()
print('ARCHIVED:' + str(len(live)))
print('DONE_COMMIT')
"""
    out = shell(db, script, timeout=600)
    if 'DONE_COMMIT' not in out:
        raise RuntimeError(f'commit did not complete:\n{out}')
    deleted = _parse_int(out, 'DELETED:')
    archived = _parse_int(out, 'ARCHIVED:')
    log(f'  deleted mail.message rows: {deleted}')
    log(f'  archived discuss.channel rows (live -> archived): {archived}')
    return deleted, archived


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog='unbackfill_htf_discuss.py',
        description='Destructive P7 rollback. Default is --dry-run.',
    )
    ap.add_argument('db', help='Odoo database name (e.g. "odoo")')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('--dry-run', action='store_true', default=True,
                   help='(default) print plan only, do not mutate')
    g.add_argument('--commit', action='store_true', default=False,
                   help='actually delete + archive')
    args = ap.parse_args(argv[1:])

    db = args.db
    mode = 'COMMIT' if args.commit else 'DRY-RUN'
    log(f'=== P7 UNBACKFILL (Tier 5 destructive revert) — db={db!r} mode={mode} ===')

    stats = survey(db)

    if not args.commit:
        log('DRY-RUN — no rows touched.')
        log(f'Would delete {stats["safe_to_delete"]} mail.message rows.')
        log(f'Would archive {stats["mirrored_channels"]} discuss.channel rows.')
        log('Re-run with --commit to apply.')
        log('RECOVERY HINT: The original chatter rows on res.partner are '
            'UNTOUCHED — your real history is safe. The destructive --commit '
            'path also explicitly excludes any candidate whose model is '
            "'res.partner'.")
        return 0

    if stats['safe_to_delete'] == 0 and stats['mirrored_channels'] == 0:
        log('Nothing to do — no mirrored rows or channels found.')
        return 0

    log('COMMIT mode — proceeding to mutate the database.')
    deleted, archived = commit_delete(db)
    log('=== DONE ===')
    log(f'Summary: deleted {deleted} mail.message rows, archived '
        f'{archived} discuss.channel rows.')
    log('RECOVERY HINT: The original chatter rows on res.partner are '
        'UNTOUCHED — your real history is safe. The mirrored Discuss '
        'history is gone; restore from a PG backup if you need it back.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
