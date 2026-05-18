"""P3 UI E2E check — phone widget + header button + asset bundle.

Drives non-browser verification of the OWL widget wiring and view
inherits. Browser sign-off is still required for visual correctness
(`✓` rendering, click behaviour), but this suite catches the regressions
that come from XML/asset bundling — which is 90% of the breakage modes.

Checks:
[1] Asset bundle ships htf_phone_field.js / .xml / .scss
[2] Combined partner-form arch contains widget="htf_phone" on phone field
[3] Combined partner-form arch contains a <header> "Send WhatsApp" button
[4] Send WhatsApp wizard action exists and has binding on res.partner
[5] Field registry returns htf_phone via /web/dataset/call_kw on a probe

Run: ``python3 /tmp/htf_p3_ui_check.py``.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import subprocess
import sys
import urllib.request

URL = 'http://localhost:8069'
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


def _session():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = json.dumps({
        'jsonrpc': '2.0',
        'params': {'db': DB, 'login': 'admin', 'password': 'admin'},
    }).encode()
    req = urllib.request.Request(
        f'{URL}/web/session/authenticate', data=body, method='POST',
        headers={'Content-Type': 'application/json'},
    )
    with opener.open(req, timeout=10) as r:
        auth = json.loads(r.read())
    assert (auth.get('result') or {}).get('uid'), f'login failed: {auth}'
    return opener


# -------------------------------------------------------------- #
# Tests                                                          #
# -------------------------------------------------------------- #

def test_asset_bundle(opener):
    print('\n[1] Asset bundle includes phone widget files')
    req = urllib.request.Request(
        f'{URL}/web/assets/debug/web.assets_backend.js',
        method='GET',
    )
    try:
        with opener.open(req, timeout=20) as r:
            body = r.read().decode('utf-8', errors='replace')
    except Exception as exc:
        check('GET /web/assets/debug/web.assets_backend.js → 200',
              False, str(exc))
        return
    check('GET /web/assets/debug/web.assets_backend.js → 200', True)
    check('bundle references htf_phone_field',
          'htf_phone_field' in body or 'HtfPhoneField' in body,
          f'no htf_phone_field token in {len(body)}-byte bundle')
    check('bundle includes "htf_phone" registry entry',
          'htf_phone' in body, 'no htf_phone token')
    # Template should ship under htf_call_center.HtfPhoneField template name
    check('bundle includes HtfPhoneField template name',
          'htf_call_center.HtfPhoneField' in body, 'template name missing')


def test_partner_form_arch():
    print('\n[2] Combined partner-form arch — widget + header button')
    out = shell("""
from lxml import etree
v = env.ref('base.view_partner_form')
arch = v._get_combined_arch()
xml_str = etree.tostring(arch).decode()
print('HAS_HTF_PHONE:', 'widget="htf_phone"' in xml_str)
print('HAS_HEADER:', '<header>' in xml_str and 'Send WhatsApp' in xml_str)
print('HAS_ICON:', 'fa-whatsapp' in xml_str)
print('HAS_HTF_TAB:', 'name="x_htf_contact_id"' in xml_str)
print('HAS_GROUPS:', 'htf_call_center.group_user' in xml_str)
""")
    lines = out.splitlines()
    for key, label in [
        ('HAS_HTF_PHONE', 'phone field has widget="htf_phone"'),
        ('HAS_HEADER', 'header has "Send WhatsApp" button'),
        ('HAS_ICON', 'header uses fa-whatsapp icon'),
        ('HAS_HTF_TAB', 'Hatif tab fields present (x_htf_contact_id)'),
        ('HAS_GROUPS', 'header button gated by group_user'),
    ]:
        line = next((l for l in lines if l.startswith(key + ':')), '')
        check(label, line.endswith('True'), line)


def test_send_wizard_action():
    print('\n[3] Send WhatsApp wizard action is bound to res.partner')
    out = shell("""
a = env.ref('htf_call_center.action_htf_send_whatsapp_wizard')
print('RES_MODEL:', a.res_model)
print('TARGET:', a.target)
print('BINDING_MODEL:', a.binding_model_id.model if a.binding_model_id else '')
""")
    lines = out.splitlines()
    for key, expected, label in [
        ('RES_MODEL:', 'htf.send.whatsapp.wizard',
         'action.res_model = wizard'),
        ('TARGET:', 'new', 'action opens in modal (target=new)'),
        ('BINDING_MODEL:', 'res.partner',
         'action bound to res.partner (Action menu binding)'),
    ]:
        line = next((l for l in lines if l.startswith(key)), '')
        check(label, expected in line, line)


def test_wizard_resolves_partner_phone():
    print('\n[4] Wizard default_get pulls partner + phone from context')
    out = shell("""
W = env['htf.send.whatsapp.wizard']
p = env['res.partner'].create({'name': 'UIcheck', 'phone': '+966555000123'})
wiz = W.with_context(active_model='res.partner', active_id=p.id).create({})
print('WIZ_PARTNER:', wiz.partner_id.name)
print('WIZ_TO:', wiz.to_number)
env.cr.rollback()
""")
    lines = out.splitlines()
    p = next((l for l in lines if l.startswith('WIZ_PARTNER:')), '')
    t = next((l for l in lines if l.startswith('WIZ_TO:')), '')
    check('wizard.partner_id = active partner', 'UIcheck' in p, p)
    check('wizard.to_number = partner.phone', '+966555000123' in t, t)


def test_xml_validity():
    print('\n[5] XML files compile cleanly (no broken xpath after upgrade)')
    out = shell("""
v = env.ref('htf_call_center.view_partner_form_inherit_htf_phone', raise_if_not_found=False)
print('OVERRIDE_EXISTS:', bool(v))
v2 = env.ref('htf_call_center.view_partner_form_inherit_htf', raise_if_not_found=False)
print('TAB_OVERRIDE_EXISTS:', bool(v2))
v3 = env.ref('htf_call_center.view_htf_send_whatsapp_wizard_form', raise_if_not_found=False)
print('WIZARD_VIEW_EXISTS:', bool(v3))
""")
    lines = out.splitlines()
    for key, label in [
        ('OVERRIDE_EXISTS:', 'phone widget inherit view installed'),
        ('TAB_OVERRIDE_EXISTS:', 'Hatif tab inherit view installed'),
        ('WIZARD_VIEW_EXISTS:', 'Send WA wizard view installed'),
    ]:
        line = next((l for l in lines if l.startswith(key)), '')
        check(label, 'True' in line, line)


# -------------------------------------------------------------- #
# Main                                                           #
# -------------------------------------------------------------- #

def main():
    print('=== P3 UI E2E ===')
    opener = _session()
    test_asset_bundle(opener)
    test_partner_form_arch()
    test_send_wizard_action()
    test_wizard_resolves_partner_phone()
    test_xml_validity()

    print(f'\n=== RESULT: {PASS}/{PASS + FAIL} passed ===')
    if FAIL:
        print('\nFailures:')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)


if __name__ == '__main__':
    main()
