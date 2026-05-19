"""P7.6 — Backfill Hatif Discuss channels from existing htf.call + htf.message.

For every res.partner with any Hatif activity (htf.call or htf.message
rows), ensure the per-partner Hatif Discuss channel exists and replay
every historical event into it as a mail.message tagged with the
mt_htf_mirror subtype. Calls get the recording attached as a native
voice-note.

Idempotent — re-running creates no duplicates because every mirror
write carries a deterministic RFC2822 message_id
(htf-msg-<id>/htf-call-<id>@htf_call_center) that the backfill checks
before writing.

Usage:
    python3 backfill_htf_discuss.py <db>

The feature flags MUST be on (master + inbound + calls). The script
turns them on temporarily for the backfill window if needed, then
restores their original state. Use --keep-flags-on to leave them on.

Reversal: run unbackfill_htf_discuss.py with --commit (see the
P7_REVERT_RUNBOOK.md for the full procedure).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys

# Default container name is the local-dev `odoo-app`. Override with
# `HTF_CONTAINER=web-erp-amro-pro python3 backfill_htf_discuss.py numo`
# on environments where the Odoo container has a different name.
CONTAINER = os.environ.get('HTF_CONTAINER', 'odoo-app')


def log(msg: str) -> None:
    ts = _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] {msg}', flush=True)


def shell(db: str, script: str) -> str:
    """Run a python snippet inside the Odoo container."""
    proc = subprocess.run(
        [
            'docker', 'exec', '-i', CONTAINER,
            'odoo', 'shell', '-d', db, '--no-http', '--log-level=error',
        ],
        input=script.encode(), capture_output=True, timeout=300,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode('utf-8', errors='replace'))
        raise RuntimeError(f'odoo shell exited {proc.returncode}')
    return proc.stdout.decode('utf-8', errors='replace')


BACKFILL_SCRIPT = r"""
from datetime import datetime
from odoo.addons.htf_call_center.services import discuss_mirror

cfg = env['htf.config']
prev_master = cfg.get_param('discuss_mirror_enabled')
prev_inbound = cfg.get_param('discuss_mirror_inbound')
prev_calls = cfg.get_param('discuss_mirror_calls')
prev_ui = cfg.get_param('discuss_ui_override')

# Force flags ON for the backfill window so the mirror functions
# don't no-op.
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)
cfg.set_param('discuss_mirror_calls', True)
# UI override flag is left at its prior value — flipping it shouldn't
# affect backfill correctness (it only governs frontend rendering).

# 1. Find every partner with any Hatif activity.
partners_from_msgs = env['htf.message'].sudo().read_group(
    [('partner_id', '!=', False)],
    ['partner_id'],
    ['partner_id'],
)
partners_from_calls = env['htf.call'].sudo().read_group(
    [('partner_id', '!=', False)],
    ['partner_id'],
    ['partner_id'],
)
partner_ids = sorted({
    row['partner_id'][0] for row in partners_from_msgs if row.get('partner_id')
} | {
    row['partner_id'][0] for row in partners_from_calls if row.get('partner_id')
})
print(f'BACKFILL_PARTNERS_FOUND:{len(partner_ids)}')

KEEP_FLAGS_ON = bool({{KEEP_FLAGS_ON}})

# 2. Iterate per partner, batching commits every 25 to avoid one
# pathological partner exploding the transaction.
posted_calls = 0
posted_msgs = 0
skipped_msgs = 0
skipped_calls = 0
created_channels = 0
errored_partners = []

for batch_start in range(0, len(partner_ids), 25):
    batch = partner_ids[batch_start:batch_start + 25]
    for pid in batch:
        partner = env['res.partner'].browse(pid).sudo()
        if not partner.exists():
            continue
        try:
            channel = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(partner)
        except Exception as exc:
            errored_partners.append((pid, f'ensure_channel: {exc}'))
            continue
        if not channel:
            errored_partners.append((pid, 'ensure_channel returned empty'))
            continue
        existed_before = bool(env['mail.message'].sudo().search_count([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
        ]))
        if not existed_before:
            created_channels += 1

        # 3. Collect all events (htf.message + htf.call) for this partner,
        # sorted by source timestamp ascending — replays history in order.
        msgs = env['htf.message'].sudo().search(
            [('partner_id', '=', pid)], order='created_at asc',
        )
        calls = env['htf.call'].sudo().search(
            [('partner_id', '=', pid)], order='created_at asc',
        )

        for m in msgs:
            wanted_msg_id = f'<htf-msg-{m.id}@htf_call_center>'
            already = env['mail.message'].sudo().search_count([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', channel.id),
                ('message_id', '=', wanted_msg_id),
            ])
            if already:
                skipped_msgs += 1
                continue
            payload = {'conversationId': m.conversation_uuid}
            try:
                if (m.direction or '').lower() == 'inbound':
                    discuss_mirror.mirror_inbound_wa(env, partner, m, payload)
                else:
                    discuss_mirror.mirror_outbound_wa_from_hatif(env, partner, m, payload)
                posted_msgs += 1
            except Exception as exc:
                errored_partners.append((pid, f'msg {m.id}: {exc}'))

        for c in calls:
            wanted_msg_id = f'<htf-call-{c.id}@htf_call_center>'
            already = env['mail.message'].sudo().search_count([
                ('model', '=', 'discuss.channel'),
                ('res_id', '=', channel.id),
                ('message_id', '=', wanted_msg_id),
            ])
            if already:
                skipped_calls += 1
                continue
            payload = {'conversationId': c.contact_uuid}
            try:
                discuss_mirror.mirror_call(env, partner, c, payload)
                posted_calls += 1
            except Exception as exc:
                errored_partners.append((pid, f'call {c.id}: {exc}'))

    env.cr.commit()
    print(f'BATCH_COMMIT batch_start={batch_start} cumulative_msgs={posted_msgs} cumulative_calls={posted_calls}')

# 4. Restore flags unless the caller wants them left on.
if not KEEP_FLAGS_ON:
    cfg.set_param('discuss_mirror_enabled', prev_master)
    cfg.set_param('discuss_mirror_inbound', prev_inbound)
    cfg.set_param('discuss_mirror_calls', prev_calls)
    cfg.set_param('discuss_ui_override', prev_ui)
    env.cr.commit()
    print(f'FLAGS_RESTORED master={prev_master} inbound={prev_inbound} calls={prev_calls} ui={prev_ui}')
else:
    print('FLAGS_KEPT_ON per --keep-flags-on')

print(f'SUMMARY created_channels={created_channels} msgs_posted={posted_msgs} msgs_skipped={skipped_msgs} '
      f'calls_posted={posted_calls} calls_skipped={skipped_calls} errors={len(errored_partners)}')
if errored_partners:
    print('FIRST_20_ERRORS:')
    for pid, reason in errored_partners[:20]:
        print(f'  partner={pid}  {reason}')
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('db', help='Odoo database name (e.g., odoo, numo)')
    parser.add_argument(
        '--keep-flags-on', action='store_true',
        help='Leave the feature flags ON after backfill (default: restore previous values).',
    )
    args = parser.parse_args()

    log(f'Starting backfill against db={args.db} keep_flags_on={args.keep_flags_on}')
    log('Phase 1/1: replay htf.message + htf.call into per-partner Discuss channels')
    script = BACKFILL_SCRIPT.replace(
        '{{KEEP_FLAGS_ON}}', '1' if args.keep_flags_on else '0',
    )
    try:
        out = shell(args.db, script)
    except RuntimeError as exc:
        log(f'FAILED: {exc}')
        return 1
    print(out)
    log('Backfill complete.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
