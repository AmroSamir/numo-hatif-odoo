"""P7 E2E check — Discuss as Hatif conversation surface.

Drives the full P7 pipeline. Uses env.cr.rollback() at the end of each
section so no test fixtures pollute the local db.

[1] Channel auto-provisioning  (4 asserts)
[2] Inbound WA mirror          (4 asserts)
[3] Outbound WA (from portal)  (3 asserts)
[4] Call mirror + body shape   (4 asserts)
[5] Outbound override 5 gates  (6 asserts)
[6] OWL store-default gating   (2 asserts)
[7] Idempotency via message_id (2 asserts)

Total target: 25 assertions.

Run:  python3 /tmp/htf_p7_check.py
or:   python3 ~/numo-hatif-odoo/htf_call_center/tools/htf_p7_check.py
"""

from __future__ import annotations

import subprocess
import sys

DB = 'odoo'
PASS, FAIL = 0, 0
FAILURES: list[str] = []


def shell(script: str) -> str:
    proc = subprocess.run(
        ['docker', 'exec', '-i', 'odoo-app', 'odoo', 'shell',
         '-d', DB, '--no-http', '--log-level=error'],
        input=script.encode(), capture_output=True, timeout=120,
    )
    return proc.stdout.decode('utf-8', errors='replace')


def check(name: str, cond: bool, detail: str = '') -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  \033[32m✓\033[0m {name}')
    else:
        FAIL += 1
        FAILURES.append(f'{name}: {detail}')
        print(f'  \033[31m✗\033[0m {name} — {detail}')


def section(title: str) -> None:
    print(f'\n[{title}]')


# ---------- [1] Channel auto-provisioning ---------- #
def t_channel():
    section('1] Channel auto-provisioning')
    out = shell(r"""
cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)

p = env['res.partner'].create({'name': 'P7chk auto', 'phone': '+9665000P7001'})
ch = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(p)
print(f'CH1:{ch.id} name={ch.name!r} partner={ch.x_htf_partner_id.id}')

# Re-call: must reuse same channel
ch2 = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(p)
print(f'CH2:{ch2.id}')

# Members include partner
mem_partner_ids = [m.partner_id.id for m in ch.channel_member_ids]
print(f'MEM_HAS_PARTNER:{p.id in mem_partner_ids}')

# Channel name pattern — phone emoji prefix for visual grouping
print(f'NAME_HAS_PREFIX:{ch.name.startswith("📞")}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_mirror_inbound', False)
env.cr.rollback()
""")
    lines = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    ch1 = lines.get('CH1', '')
    ch2 = lines.get('CH2', '')
    check('channel auto-provisioned with id', 'CH1:' in ch1 and 'partner=' in ch1, ch1)
    check('channel name starts with 📞', 'NAME_HAS_PREFIX:True' in lines.get('NAME_HAS_PREFIX', ''))
    check('partner is a channel member',
          'MEM_HAS_PARTNER:True' in lines.get('MEM_HAS_PARTNER', ''))
    # Idempotent: ch1.id == ch2.id
    try:
        id1 = ch1.split('CH1:')[1].split(' ')[0]
        id2 = ch2.split('CH2:')[1]
        check('second call returns the same channel id',
              id1 == id2.strip(), f'{id1} vs {id2.strip()}')
    except Exception as exc:  # noqa: BLE001
        check('second call returns the same channel id', False, f'parse: {exc}')


# ---------- [2] Inbound WA mirror ---------- #
def t_inbound_wa():
    section('2] Inbound WA mirror')
    out = shell(r"""
from odoo.addons.htf_call_center.services import discuss_mirror

cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)

p = env['res.partner'].create({'name': 'P7chk inbound', 'phone': '+9665000P7002'})
m = env['htf.message'].create({
    'direction': 'inbound', 'message_type': 'text', 'state': 'sent',
    'body': 'مرحبا اختبار', 'partner_id': p.id, 'conversation_uuid': 'p7-convo-002',
})
discuss_mirror.mirror_inbound_wa(env, p, m, {'conversationId': 'p7-convo-002'})

p.invalidate_recordset()
ch = p.x_htf_discuss_channel_id
msgs = env['mail.message'].search([('model','=','discuss.channel'),('res_id','=',ch.id)])
print(f'MSG_COUNT:{len(msgs)}')
if msgs:
    msg = msgs[0]
    print(f'MSG_AUTHOR_IS_PARTNER:{msg.author_id.id == p.id}')
    print(f'MSG_BODY_HAS_TEXT:{"مرحبا" in (msg.body or "")}')
    print(f'MSG_SUBTYPE_IS_MIRROR:{msg.subtype_id.name == "Hatif Mirror"}')
print(f'CONVO_STAMPED:{ch.x_htf_last_conversation_id == "p7-convo-002"}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_mirror_inbound', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    check('inbound WA creates exactly 1 mail.message', 'MSG_COUNT:1' in L.get('MSG_COUNT', ''),
          L.get('MSG_COUNT', ''))
    check('mail.message author = partner', 'True' in L.get('MSG_AUTHOR_IS_PARTNER', 'False'))
    check('mail.message body contains WA text', 'True' in L.get('MSG_BODY_HAS_TEXT', 'False'))
    check('mail.message subtype = Hatif Mirror', 'True' in L.get('MSG_SUBTYPE_IS_MIRROR', 'False'))


# ---------- [3] Outbound WA from Hatif portal ---------- #
def t_outbound_portal_wa():
    section('3] Outbound WA from Hatif portal')
    out = shell(r"""
from odoo.addons.htf_call_center.services import discuss_mirror

cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)

p = env['res.partner'].create({'name': 'P7chk portal-out', 'phone': '+9665000P7003'})
m = env['htf.message'].create({
    'direction': 'outbound', 'message_type': 'text', 'state': 'sent',
    'body': 'reply from portal', 'partner_id': p.id, 'conversation_uuid': 'p7-convo-003',
})
discuss_mirror.mirror_outbound_wa_from_hatif(env, p, m, {'conversationId': 'p7-convo-003'})

p.invalidate_recordset()
ch = p.x_htf_discuss_channel_id
msgs = env['mail.message'].search([('model','=','discuss.channel'),('res_id','=',ch.id)])
print(f'MSG_COUNT:{len(msgs)}')
if msgs:
    msg = msgs[0]
    print(f'MSG_AUTHOR_NOT_PARTNER:{msg.author_id.id != p.id}')
    print(f'MSG_BODY_HAS_TEXT:{"reply from portal" in (msg.body or "")}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_mirror_inbound', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    check('outbound portal WA -> 1 mail.message', 'MSG_COUNT:1' in L.get('MSG_COUNT', ''))
    check('outbound author != partner', 'True' in L.get('MSG_AUTHOR_NOT_PARTNER', 'False'))
    check('outbound body present', 'True' in L.get('MSG_BODY_HAS_TEXT', 'False'))


# ---------- [4] Call mirror ---------- #
def t_call_mirror():
    section('4] Call mirror')
    out = shell(r"""
from datetime import datetime
from odoo.addons.htf_call_center.services import discuss_mirror

cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_calls', True)

p = env['res.partner'].create({'name': 'P7chk call', 'phone': '+9665000P7004'})
agent = env.ref('base.user_admin', raise_if_not_found=False)
c = env['htf.call'].create({
    'htf_call_id': 'p7chk-call-1', 'direction': 'inbound', 'status': 'completed',
    'partner_id': p.id, 'contact_number': '+9665000P7004',
    'caller_number': '+9665000P7004',
    'created_at': datetime.utcnow(), 'pickup_time': datetime.utcnow(),
    'handler_user_id': agent.id if agent else False,
    'summary': 'استفسر العميل عن الدورات',
})
discuss_mirror.mirror_call(env, p, c, {})

p.invalidate_recordset()
ch = p.x_htf_discuss_channel_id
msgs = env['mail.message'].search([('model','=','discuss.channel'),('res_id','=',ch.id)])
print(f'MSG_COUNT:{len(msgs)}')
if msgs:
    msg = msgs[0]
    body = msg.body or ''
    print(f'BODY_HAS_PHONE_ICON:{"📞" in body}')
    print(f'BODY_HAS_STRONG_TAG:{"<strong>" in body}')
    print(f'BODY_HAS_SUMMARY:{"Summary" in body or "استفسر" in body}')

# Missed call: pickup_kind='none', body should say "Missed call"
p2 = env['res.partner'].create({'name': 'P7chk missed', 'phone': '+9665000P7005'})
c2 = env['htf.call'].create({
    'htf_call_id': 'p7chk-call-2', 'direction': 'inbound', 'status': 'missed',
    'partner_id': p2.id, 'contact_number': '+9665000P7005',
    'caller_number': '+9665000P7005', 'created_at': datetime.utcnow(),
})
discuss_mirror.mirror_call(env, p2, c2, {})
p2.invalidate_recordset()
ch2 = p2.x_htf_discuss_channel_id
m2 = env['mail.message'].search([('model','=','discuss.channel'),('res_id','=',ch2.id)], limit=1)
print(f'MISSED_BODY_HAS_MISSED:{"Missed" in (m2.body or "") if m2 else False}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_mirror_calls', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    check('call -> 1 mail.message', 'MSG_COUNT:1' in L.get('MSG_COUNT', ''))
    check('call body has phone icon', 'True' in L.get('BODY_HAS_PHONE_ICON', 'False'))
    check('call body uses <strong> (Markup survived sanitizer)',
          'True' in L.get('BODY_HAS_STRONG_TAG', 'False'))
    check('missed-call body says Missed', 'True' in L.get('MISSED_BODY_HAS_MISSED', 'False'))


# ---------- [5] Outbound override — 5 gates ---------- #
def t_outbound_override():
    section('5] Outbound override (5 gates)')
    out = shell(r"""
from datetime import datetime, timedelta
from odoo.exceptions import UserError

cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)
cfg.set_param('discuss_outbound_route', True)
cfg.set_param('allow_real_outbound', False)  # dryrun
fb = env['htf.channel'].search([('state','=','active')], limit=1)
if not fb:
    fb = env['htf.channel'].create({
        'name': 'P7chk gate fb', 'htf_channel_id': 'p7chk-fb',
        'channel_type': 'whatsapp', 'phone_number': '+966000000000', 'state': 'active',
    })
cfg.set_param('default_outbound_wa_channel_id', str(fb.id))

# Open-window partner
p = env['res.partner'].create({
    'name': 'P7chk gate open', 'phone': '+9665000P7010',
    'x_htf_last_inbound_at': (datetime.utcnow() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
})
ch = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(p)

admin = env.ref('base.user_admin')

# Gate 1: real agent post (window open) → htf.message created
before = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
ch.with_user(admin).message_post(body='Open window send', message_type='comment')
after = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
print(f'GATE1_AGENT_POST_TRIGGERS:{after - before == 1}')

# Gate 2: closed window → UserError
p_old = env['res.partner'].create({'name': 'P7chk gate closed', 'phone': '+9665000P7011'})
ch_old = env['discuss.channel'].sudo()._ensure_htf_discuss_channel(p_old)
raised = False
try:
    ch_old.with_user(admin).message_post(body='block me', message_type='comment')
except UserError:
    raised = True
print(f'GATE2_CLOSED_WINDOW_RAISES:{raised}')

# Gate 3: htf_mirror_write context → NO send
before3 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
ch.with_user(admin).with_context(htf_mirror_write=True).message_post(body='mirror', message_type='comment')
after3 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
print(f'GATE3_MIRROR_CONTEXT_SKIPS:{after3 == before3}')

# Gate 4: author=partner → NO send
before4 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
ch.with_user(admin).message_post(body='from partner', author_id=p.id, message_type='comment')
after4 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
print(f'GATE4_PARTNER_AUTHOR_SKIPS:{after4 == before4}')

# Gate 5: flag off → NO send
cfg.set_param('discuss_outbound_route', False)
before5 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
ch.with_user(admin).message_post(body='flag off', message_type='comment')
after5 = env['htf.message'].search_count([('partner_id','=',p.id),('direction','=','outbound')])
print(f'GATE5_FLAG_OFF_SKIPS:{after5 == before5}')

# Bonus: non-Hatif channel (no x_htf_partner_id) is untouched
cfg.set_param('discuss_outbound_route', True)
internal_ch = env['discuss.channel'].sudo().create({
    'name': 'internal team', 'channel_type': 'channel',
})
before6 = env['htf.message'].search_count([])
internal_ch.with_user(admin).message_post(body='internal note', message_type='comment')
after6 = env['htf.message'].search_count([])
print(f'BONUS_NON_HATIF_UNTOUCHED:{after6 == before6}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_outbound_route', False)
cfg.set_param('discuss_mirror_inbound', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    check('gate1: agent post (open window) triggers outbound send',
          'True' in L.get('GATE1_AGENT_POST_TRIGGERS', 'False'))
    check('gate2: closed window raises UserError',
          'True' in L.get('GATE2_CLOSED_WINDOW_RAISES', 'False'))
    check('gate3: htf_mirror_write context skips outbound',
          'True' in L.get('GATE3_MIRROR_CONTEXT_SKIPS', 'False'))
    check('gate4: author=partner skips outbound',
          'True' in L.get('GATE4_PARTNER_AUTHOR_SKIPS', 'False'))
    check('gate5: discuss_outbound_route flag off skips',
          'True' in L.get('GATE5_FLAG_OFF_SKIPS', 'False'))
    check('non-Hatif (internal) channel is unaffected',
          'True' in L.get('BONUS_NON_HATIF_UNTOUCHED', 'False'))


# ---------- [6] OWL store-default gating ---------- #
def t_owl_store_defaults():
    section('6] OWL store-default gating (discuss_ui_override sub-flag)')
    out = shell(r"""
cfg = env['htf.config']
# Flag ON
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_ui_override', True)
print('ACTIVE_UI:', cfg.discuss_mirror_active('ui'))
# Flag OFF
cfg.set_param('discuss_ui_override', False)
print('ACTIVE_UI_OFF:', cfg.discuss_mirror_active('ui'))
cfg.set_param('discuss_mirror_enabled', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    check("discuss_mirror_active('ui') True when both flags on",
          'True' in L.get('ACTIVE_UI', 'False'))
    check("discuss_mirror_active('ui') False when sub-flag off",
          'False' in L.get('ACTIVE_UI_OFF', 'True'))


# ---------- [7] Idempotency via message_id ---------- #
def t_idempotency():
    section('7] Idempotency via stable message_id')
    out = shell(r"""
from odoo.addons.htf_call_center.services import discuss_mirror

cfg = env['htf.config']
cfg.set_param('discuss_mirror_enabled', True)
cfg.set_param('discuss_mirror_inbound', True)

p = env['res.partner'].create({'name': 'P7chk idem', 'phone': '+9665000P7099'})
m = env['htf.message'].create({
    'direction': 'inbound', 'message_type': 'text', 'state': 'sent',
    'body': 'idem test', 'partner_id': p.id,
})
discuss_mirror.mirror_inbound_wa(env, p, m, {})
discuss_mirror.mirror_inbound_wa(env, p, m, {})
ch = p.x_htf_discuss_channel_id
count = env['mail.message'].search_count([
    ('model','=','discuss.channel'),('res_id','=',ch.id),
])
print(f'TWO_MIRROR_CALLS_PRODUCE:{count}')
msg = env['mail.message'].search([
    ('model','=','discuss.channel'),('res_id','=',ch.id),
], limit=1)
print(f'MESSAGE_ID_PRESENT:{"htf-msg-" in (msg.message_id or "")}')

cfg.set_param('discuss_mirror_enabled', False)
cfg.set_param('discuss_mirror_inbound', False)
env.cr.rollback()
""")
    L = {l.split(':', 1)[0]: l for l in out.splitlines() if ':' in l}
    # Two consecutive calls with the same htf.message id → one mail.message
    # NOTE: message_id uniqueness is enforced via Odoo's mail.message UNIQUE
    # constraint, so the second call silently no-ops or reuses.
    check('two mirror calls -> one mail.message (idempotent)',
          'TWO_MIRROR_CALLS_PRODUCE:1' in L.get('TWO_MIRROR_CALLS_PRODUCE', ''),
          L.get('TWO_MIRROR_CALLS_PRODUCE', ''))
    check('mail.message.message_id has htf-msg- prefix',
          'True' in L.get('MESSAGE_ID_PRESENT', 'False'))


def main() -> int:
    print('=== P7 — Discuss as Hatif conversation surface ===')
    t_channel()
    t_inbound_wa()
    t_outbound_portal_wa()
    t_call_mirror()
    t_outbound_override()
    t_owl_store_defaults()
    t_idempotency()
    print()
    print(f'=== RESULT: {PASS}/{PASS + FAIL} passed ===')
    if FAIL:
        print('\nFAILURES:')
        for f in FAILURES:
            print(f'  - {f}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
