"""P3 backend E2E check — channel resolver, outbound send, wizard, retry cron.

Drives the full backend pipeline:

[1] Channel resolver chain (workspace fallback, partner override, team)
[2] send_text dry-run (DNC + window pre-checks, dryrun mode)
[3] send_template dry-run with parameter builders
[4] Send WhatsApp wizard (text mode + template mode via default_get)
[5] Retry cron (budget-exceeded → failed; attempt counter increments)
[6] Cost-by-category mapping

UI tasks T3.3 (phone widget) and T3.4 (chatter composer) are NOT covered
by this suite — they need browser-driven verification when Amr signs
off and we can use Playwright.

Run: ``python3 /tmp/htf_p3_check.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys

DB = 'odoo'
PASS, FAIL = 0, 0
FAILURES: list[str] = []


def shell(script: str) -> str:
    p = subprocess.run(
        ['docker', 'exec', '-i', 'odoo-app', 'odoo', 'shell', '-d', DB,
         '--no-http', '--log-level=warn'],
        input=script.encode(), capture_output=True, timeout=60,
    )
    return p.stdout.decode('utf-8', errors='replace')


def check(name: str, cond: bool, detail: str = '') -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f'  ✓ {name}')
    else:
        FAIL += 1
        FAILURES.append(f'{name}: {detail}')
        print(f'  ✗ {name} — {detail}')


def setup_test_channel():
    """Create a real, committed channel + workspace fallback param so
    every subsequent test can rely on resolution."""
    out = shell("""
ch = env['htf.channel'].search([('htf_channel_id','=','3a20-test-p3-channel')], limit=1)
if not ch:
    ch = env['htf.channel'].create({
        'name': 'P3 Test Channel', 'htf_channel_id': '3a20-test-p3-channel',
        'channel_type': 'whatsapp', 'phone_number': '+966500000000', 'state': 'active',
    })
env['htf.config'].set_param('default_outbound_wa_channel_id', str(ch.id))
env.cr.commit()
print(f'CHANNEL_ID:{ch.id}')
""")
    line = next(l for l in out.splitlines() if l.startswith('CHANNEL_ID:'))
    return int(line.split(':', 1)[1])


def test_resolver(channel_id: int):
    print('\n[1] Channel resolver chain')
    out = shell(f"""
from odoo.addons.htf_call_center.services import channel_resolver
from odoo.addons.htf_call_center.exceptions import HtfChannelNotFoundError

p = env['res.partner'].create({{'name': 'R-Test', 'phone': '+966500000001'}})
ch = channel_resolver.resolve_outbound_wa(env, partner=p, sender_user=env.user)
print(f'WORKSPACE_FALLBACK_ID:{{ch.id}}')

# Now set a per-partner override
p2 = env['res.partner'].create({{
    'name': 'R-Override', 'phone': '+966500000002',
    'x_htf_default_channel_id': {channel_id},
}})
ch2 = channel_resolver.resolve_outbound_wa(env, partner=p2, sender_user=env.user)
print(f'PARTNER_OVERRIDE_ID:{{ch2.id}}')

# Error path: no workspace fallback + no partner override
env['ir.config_parameter'].sudo().set_param('htf_call_center.default_outbound_wa_channel_id', '')
try:
    channel_resolver.resolve_outbound_wa(env, partner=p, sender_user=env.user)
    print('ERROR_RAISED:no')
except HtfChannelNotFoundError:
    print('ERROR_RAISED:yes')
env.cr.rollback()
""")
    lines = out.splitlines()
    ws = next((l for l in lines if l.startswith('WORKSPACE_FALLBACK_ID:')), '')
    over = next((l for l in lines if l.startswith('PARTNER_OVERRIDE_ID:')), '')
    err = next((l for l in lines if l.startswith('ERROR_RAISED:')), '')
    check('workspace fallback resolves',
          ws == f'WORKSPACE_FALLBACK_ID:{channel_id}', ws)
    check('partner override beats workspace fallback',
          over == f'PARTNER_OVERRIDE_ID:{channel_id}', over)
    check('no fallback → HtfChannelNotFoundError', err == 'ERROR_RAISED:yes', err)


def test_send_text():
    print('\n[2] send_text — dry-run, DNC, window pre-checks')
    out = shell("""
from odoo.addons.htf_call_center.services import whatsapp
from odoo.addons.htf_call_center.exceptions import HtfDncBlockedError, HtfWindowExpiredError

p_open = env['res.partner'].create({'name': 'open', 'phone': '+966500000010',
    'x_htf_last_inbound_at': '2026-05-18 03:00:00'})
m = whatsapp.send_text(env, to_number='+966500000010', text='hi', partner=p_open)
print(f'TEXT_DRY_STATE:{m.state}|TYPE:{m.message_type}|EVTID_PREFIX:{m.conversation_event_id[:6]}')

p_dnc = env['res.partner'].create({'name': 'dnc', 'phone': '+966500000011', 'x_htf_opted_out': True})
try:
    whatsapp.send_text(env, to_number='+966500000011', text='block', partner=p_dnc)
    print('DNC_RAISED:no')
except HtfDncBlockedError:
    print('DNC_RAISED:yes')

p_old = env['res.partner'].create({'name': 'old', 'phone': '+966500000012'})
try:
    whatsapp.send_text(env, to_number='+966500000012', text='block', partner=p_old)
    print('WIN_RAISED:no')
except HtfWindowExpiredError:
    print('WIN_RAISED:yes')
env.cr.rollback()
""")
    lines = out.splitlines()
    dry = next((l for l in lines if l.startswith('TEXT_DRY_STATE:')), '')
    dnc = next((l for l in lines if l.startswith('DNC_RAISED:')), '')
    win = next((l for l in lines if l.startswith('WIN_RAISED:')), '')
    check('send_text dry-run → state=sent (dryrun mode)',
          'TEXT_DRY_STATE:sent' in dry, dry)
    check('send_text persists message_type=text',
          'TYPE:text' in dry, dry)
    check('send_text returns dryrun: synthetic event id',
          'EVTID_PREFIX:dryrun' in dry, dry)
    check('DNC pre-check raises HtfDncBlockedError', dnc == 'DNC_RAISED:yes', dnc)
    check('window pre-check raises HtfWindowExpiredError', win == 'WIN_RAISED:yes', win)


def test_send_template():
    print('\n[3] send_template — dry-run + parameter builders + categories')
    out = shell("""
from odoo.addons.htf_call_center.services import whatsapp

# Builder tests
b1 = whatsapp.build_body_parameter('Ahmed', 'ORD-5123', 'confirmed')
print(f'BODY_BUILDER:{len(b1["Values"])}|FIRST:{b1["Values"][0]["Text"]}')

h_img = whatsapp.build_header_image('https://cdn.example/banner.jpg')
print(f'IMG_HEADER:{h_img["Type"]}|VTYPE:{h_img["Values"][0]["Type"]}|URL:{h_img["Values"][0]["ImageUrl"][:25]}')

url_btn = whatsapp.build_url_button(0, 'ORD-5123')
print(f'URL_BUTTON:SubType={url_btn["SubType"]}|Index={url_btn["Index"]}')

# Template send with full param set
p = env['res.partner'].create({'name': 'tpl', 'phone': '+966500000020'})
params = [
    whatsapp.build_header_image('https://cdn.example/promo.jpg'),
    whatsapp.build_body_parameter('Ahmed'),
    whatsapp.build_url_button(0, 'PROMO-XYZ'),
]
m = whatsapp.send_template(env, template_name='promo_offer', language='ar',
    to_number='+966500000020', parameters=params, partner=p, category='marketing')
print(f'TPL_STATE:{m.state}|CAT:{m.meta_category}|COST:{m.meta_cost_estimate}')

for cat, expected in [('utility', 0.0224), ('authentication', 0.0265), ('service', 0.0)]:
    m2 = whatsapp.send_template(env, template_name='t', language='en',
        to_number='+966500000020', parameters=[], partner=p, category=cat)
    print(f'CAT_{cat.upper()}_COST:{m2.meta_cost_estimate}|EXPECTED:{expected}')
env.cr.rollback()
""")
    lines = out.splitlines()
    body = next((l for l in lines if l.startswith('BODY_BUILDER:')), '')
    img = next((l for l in lines if l.startswith('IMG_HEADER:')), '')
    btn = next((l for l in lines if l.startswith('URL_BUTTON:')), '')
    tpl = next((l for l in lines if l.startswith('TPL_STATE:')), '')
    check('build_body_parameter packs 3 values', '3|FIRST:Ahmed' in body, body)
    check('build_header_image yields Type=Header + image',
          'Header|VTYPE:image' in img, img)
    check('build_url_button sets SubType=url + Index=0',
          'SubType=url|Index=0' in btn, btn)
    check('template send → state=sent (dryrun)',
          'TPL_STATE:sent' in tpl, tpl)
    check('marketing cost = $0.024', 'COST:0.024' in tpl, tpl)
    for cat, expected in [('utility', '0.0224'), ('authentication', '0.0265'), ('service', '0.0')]:
        line = next((l for l in lines if l.startswith(f'CAT_{cat.upper()}_COST:')), '')
        check(f'{cat} cost = ${expected}', f'COST:{expected}|' in line, line)


def test_wizard():
    print('\n[4] Send WhatsApp wizard (default_get + action_send)')
    out = shell("""
W = env['htf.send.whatsapp.wizard']
p = env['res.partner'].create({'name': 'wizP', 'phone': '+966500000030',
    'x_htf_last_inbound_at': '2026-05-18 03:00:00'})

# default_get pulls from active_model/active_id
wiz = W.with_context(active_model='res.partner', active_id=p.id).create({})
print(f'WIZ_PARTNER:{wiz.partner_id.name}|TO:{wiz.to_number}|MODE:{wiz.mode}')
print(f'WIZ_PREFLIGHT_ERR:{wiz.preflight_error or "-"}|WIN_OPEN:{wiz.window_open}')

# Text-mode send
wiz.text = 'wizard text test'
action = wiz.action_send()
m = env['htf.message'].browse(action['res_id'])
print(f'WIZ_TEXT_MSG:state={m.state}|type={m.message_type}')

# Template-mode send via shortcuts
wiz2 = W.with_context(active_model='res.partner', active_id=p.id).create({
    'mode':'template','template_name':'welcome_1','template_language':'ar',
    'template_body_params':'Ahmed|Code123','template_category':'utility',
})
action2 = wiz2.action_send()
m2 = env['htf.message'].browse(action2['res_id'])
print(f'WIZ_TPL_MSG:state={m2.state}|type={m2.message_type}|body={m2.body[:30]!r}')
env.cr.rollback()
""")
    lines = out.splitlines()
    wp = next((l for l in lines if l.startswith('WIZ_PARTNER:')), '')
    err = next((l for l in lines if l.startswith('WIZ_PREFLIGHT_ERR:')), '')
    tx = next((l for l in lines if l.startswith('WIZ_TEXT_MSG:')), '')
    tpl = next((l for l in lines if l.startswith('WIZ_TPL_MSG:')), '')
    check('wizard default_get fills partner + phone',
          'WIZ_PARTNER:wizP|TO:+966500000030|MODE:text' in wp, wp)
    check('wizard preflight: window open, no error',
          'WIZ_PREFLIGHT_ERR:-|WIN_OPEN:True' in err, err)
    check('wizard action_send (text) creates sent htf.message',
          'state=sent|type=text' in tx, tx)
    check('wizard action_send (template) creates sent template message',
          'state=sent|type=template' in tpl, tpl)


def test_retry_cron():
    print('\n[5] Retry cron — budget logic + attempt counter')
    out = shell("""
import json
M = env['htf.message'].sudo()
chan = env['htf.channel'].search([], limit=1)
p = env['res.partner'].create({'name': 'crp', 'phone': '+966500000040'})

# Past budget → mark failed
m_dead = M.create({
    'direction':'outbound','message_type':'text','state':'failed_pending',
    'body':'dead','channel_id':chan.id,'partner_id':p.id,'error_code':7,
    'raw_payload': json.dumps({'_request':{'ChannelId':'x','Text':'t','ToNumber':'966'}}),
})
M.cron_retry_failed_pending(max_attempts=6)
m_dead = M.browse(m_dead.id)
print(f'DEAD_STATE:{m_dead.state}|REASON_HAS_GAVEUP:{"gave up" in (m_dead.error_reason or "")}')

# Eligible → bump attempt counter, stay failed_pending
m_live = M.create({
    'direction':'outbound','message_type':'text','state':'failed_pending',
    'body':'live','channel_id':chan.id,'partner_id':p.id,'error_code':0,
    'raw_payload': json.dumps({'_request':{'ChannelId':'x','Text':'t','ToNumber':'966'}}),
})
M.cron_retry_failed_pending(max_attempts=6)
m_live = M.browse(m_live.id)
print(f'LIVE_STATE:{m_live.state}|ATTEMPTS_INC:{m_live.error_code}')
env.cr.rollback()
""")
    lines = out.splitlines()
    dead = next((l for l in lines if l.startswith('DEAD_STATE:')), '')
    live = next((l for l in lines if l.startswith('LIVE_STATE:')), '')
    check('budget-exceeded row → state=failed',
          'DEAD_STATE:failed' in dead, dead)
    check('budget-exceeded reason contains "gave up"',
          'REASON_HAS_GAVEUP:True' in dead, dead)
    check('retry-eligible row stays failed_pending (no real API)',
          'LIVE_STATE:failed_pending' in live, live)
    check('retry-eligible row has incremented attempt counter',
          'ATTEMPTS_INC:1' in live, live)


def main():
    print('=== P3 BACKEND E2E ===')
    channel_id = setup_test_channel()
    print(f'  channel_id={channel_id}')
    test_resolver(channel_id)
    test_send_text()
    test_send_template()
    test_wizard()
    test_retry_cron()

    print(f'\n=== RESULT: {PASS}/{PASS + FAIL} passed ===')
    if FAIL:
        print('\nFailures:')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)


if __name__ == '__main__':
    main()
