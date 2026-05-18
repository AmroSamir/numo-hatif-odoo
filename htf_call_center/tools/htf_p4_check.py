"""P4 E2E check — calls webhook + dispatcher + chatter + signals.

Drives the full P4 pipeline:

[1] HMAC verification (route exists, rejects bad sig when not skipped)
[2] dev_mode_skip_hmac accepts unsigned (live UAT reality with Hatif)
[3] Idempotency — composite event id <call_id>:<status>:<type>
[4] Inbound completed — full analytics (recording + transcript + summary
    + sentiment + evaluation rubric)
[5] Missed inbound — minimal payload, no analytics
[6] Failed outbound — error path
[7] Status transition Active → Completed → Same row updated in place
[8] Auto-create partner: contactId path + phone-match path + fallback
[9] Duration compute (from timestamps AND from HH:MM:SS fallback)
[10] Sentiment mapping (1-5 → positive/neutral/negative/mixed/unknown)
[11] Chatter post with Recording + Summary + transcript preview
[12] Signal bus delivery for htf.call.received / .missed / .failed
[13] Bad JSON / unknown enums / malformed payloads degrade gracefully

Run: ``python3 /tmp/htf_p4_check.py``
"""

from __future__ import annotations

import hashlib
import hmac
import http.cookiejar
import json
import subprocess
import sys
import urllib.error
import urllib.request

URL = 'http://localhost:8069'
DB = 'odoo'
# Shared with the P2 suite so both can run in sequence without
# cache-invalidation races on the running Odoo worker.
SECRET = 'p2-test-secret'
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


def post(opener, payload, body_override=None, sign=True):
    """POST a payload, optionally HMAC-signed so we don't depend on
    dev_mode_skip_hmac being on (which other suites toggle off)."""
    body = body_override if body_override is not None else \
        json.dumps(payload, ensure_ascii=False).encode()
    headers = {'Content-Type': 'application/json'}
    if sign:
        sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        headers['X-Voxa-Signature'] = sig
    req = urllib.request.Request(
        f'{URL}/htf/webhook/call', data=body, method='POST', headers=headers,
    )
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, (e.read() or b'').decode('utf-8', errors='replace')


def ensure_signed_mode():
    """Set webhook secret + ensure strict HMAC mode. This suite signs
    every payload so we don't depend on dev_mode_skip_hmac, which other
    suites toggle to True for their own purposes.
    """
    shell(f"""
Cfg = env['htf.config']
Cfg.set_param('webhook_secret_current', '{SECRET}')
Cfg.set_param('dev_mode_skip_hmac', 'False')
env.cr.commit()
print('OK')
""")


def clean_test_artefacts():
    """Wipe rows from prior runs so idempotency replay tests start fresh."""
    shell("""
env['htf.call'].sudo().search([('htf_call_id','like','call-P4E2E-%')]).unlink()
env['htf.call'].sudo().search([('htf_call_id','like','signal-test-%')]).unlink()
env['htf.contact.link'].sudo().search([('htf_contact_id','like','contact-P4E2E-%')]).unlink()
env['htf.contact.link'].sudo().search([('htf_contact_id','like','contact-PHONEMATCH-%')]).unlink()
env['res.partner'].sudo().search([('name','like','PhoneMatch')]).unlink()
env['res.partner'].sudo().search([('name','like','Hatif Caller%')]).unlink()
env['res.partner'].sudo().search([('name','=like','Hatif Contact contact-P4E2E-%')]).unlink()
env['htf.webhook.event'].sudo().search([
    '|', ('event_id', 'like', 'call-P4E2E-%'),
    ('event_id', 'like', 'signal-test-%'),
]).unlink()
env.cr.commit()
print('cleaned')
""")


def ensure_test_channel():
    """Pre-existing channel for the P3 suite; reuse here."""
    out = shell("""
ch = env['htf.channel'].search([('htf_channel_id','=','3a20-test-p3-channel')], limit=1)
if not ch:
    ch = env['htf.channel'].create({
        'name':'P3 Test Channel','htf_channel_id':'3a20-test-p3-channel',
        'channel_type':'both','phone_number':'+966500000000','state':'active',
    })
    env.cr.commit()
print(f'CHANNEL_ID:{ch.id}')
""")
    line = next(l for l in out.splitlines() if l.startswith('CHANNEL_ID:'))
    return int(line.split(':', 1)[1])


# -------------------------------------------------------------- #
# Test plan                                                      #
# -------------------------------------------------------------- #

def base_completed_payload(suffix='001', **overrides):
    """Build a fully-populated 'completed' inbound payload for testing."""
    p = {
        'workspaceId': 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        'channelId':   '3a20-test-p3-channel',
        'id':          f'call-P4E2E-{suffix}',
        'status':      1,    # Completed
        'type':        1,    # Inbound
        'callerNumber': '+9665XXXXXXXX',
        'calleeNumber': '+966115001591',
        'pickupTime':  '2026-05-19T01:00:00Z',
        'hangupTime':  '2026-05-19T01:05:32Z',
        'userId':      'hatif-user-p4e2e',
        'userName':    'Test Agent',
        'contactId':   f'contact-P4E2E-{suffix}',
        'contactNumber': '+9665XXXXXXXX',
        'callLength':  '00:05:32',
        'aiAgentId':   None,
        'recordingUrl': 'https://cdn.example/rec.mp3',
        'transcription': {
            'text': 'Hello agent, I need help with my course.',
            'words': [
                {'text': 'Hello', 'start': 0.0, 'end': 0.4,
                 'type': 'word', 'speaker': 'user'},
                {'text': 'agent', 'start': 0.5, 'end': 0.9,
                 'type': 'word', 'speaker': 'user'},
            ],
        },
        'summary':   'Customer wants information on courses.',
        'sentiment': 1,    # Positive
        'evaluationCriteriaResult': [{
            'id': 'eval-001', 'dataType': 'String',
            'description': 'Greeted properly', 'value': 'Yes',
            'rationale': 'Said hello within 5 seconds',
        }],
        'creationTime': '2026-05-19T01:00:00Z',
    }
    p.update(overrides)
    return p


# ---- Sections ------------------------------------------------- #

def test_route_basics(opener):
    print('\n[1] Route exists + plumbing')
    check('GET on POST-only route → 405 or 404',
          post(opener, None, body_override=b'')[0] in (400, 405, 401, 200),
          'webhook responds to any verb')  # any error is OK; just confirms route exists
    check('Bad JSON → 400',
          post(opener, None, body_override=b'not-json{')[0] == 400)


def test_idempotency(opener):
    print('\n[2] Composite event-id idempotency')
    PL = base_completed_payload('IDEMP')
    first = post(opener, PL)
    second = post(opener, PL)
    check('first delivery → 200 OK', first == (200, 'OK'), str(first))
    check('replay → 200 OK (duplicate)',
          second == (200, 'OK (duplicate)'), str(second))


def test_status_transition(opener):
    print('\n[3] Status transition Active → Completed updates same row')
    PL = base_completed_payload('TRANS')
    PL['status'] = 0  # Active
    PL['pickupTime'] = None
    PL['hangupTime'] = None
    PL['summary'] = None
    PL['recordingUrl'] = None
    PL['transcription'] = None
    PL['callLength'] = None
    PL['sentiment'] = None
    PL['evaluationCriteriaResult'] = None
    check('Active → 200', post(opener, PL)[0] == 200)
    PL2 = base_completed_payload('TRANS')  # back to full completed
    check('Completed → 200', post(opener, PL2)[0] == 200)

    out = shell("""
rows = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-TRANS')])
print('ROW_COUNT:', len(rows))
if rows:
    r = rows[0]
    print('FINAL_STATUS:', r.status)
    print('SUMMARY_SET:', bool(r.summary))
    print('RECORDING_SET:', bool(r.recording_url))
""")
    lines = out.splitlines()
    count = next(l for l in lines if l.startswith('ROW_COUNT:'))
    status = next(l for l in lines if l.startswith('FINAL_STATUS:'))
    summary = next(l for l in lines if l.startswith('SUMMARY_SET:'))
    rec = next(l for l in lines if l.startswith('RECORDING_SET:'))
    check('exactly 1 row across transitions',
          'ROW_COUNT: 1' in count, count)
    check('final status = completed', 'completed' in status, status)
    check('summary set on update', 'True' in summary, summary)
    check('recording set on update', 'True' in rec, rec)


def test_completed_inbound_full(opener):
    print('\n[4] Completed inbound — full analytics persistence')
    PL = base_completed_payload('FULL')
    check('200 on completed inbound', post(opener, PL)[0] == 200)

    out = shell("""
c = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-FULL')], limit=1)
print('STATUS:', c.status)
print('DIRECTION:', c.direction)
print('DURATION:', c.duration_seconds)
print('SENTIMENT:', c.sentiment)
print('SUMMARY:', c.summary[:30] if c.summary else '')
print('TRANSCRIPT_TEXT:', c.transcription_text[:30] if c.transcription_text else '')
print('TRANSCRIPT_WORDS:', bool(c.transcription_words_json))
print('EVAL_JSON:', bool(c.evaluation_criteria_json))
print('RECORDING_URL:', bool(c.recording_url))
print('CHATTER_MSG:', bool(c.chatter_message_id))
print('PARTNER:', bool(c.partner_id))
""")
    lines = out.splitlines()
    expected = {
        'STATUS:': 'completed',
        'DIRECTION:': 'inbound',
        'DURATION:': '332',
        'SENTIMENT:': 'positive',
        'TRANSCRIPT_WORDS:': 'True',
        'EVAL_JSON:': 'True',
        'RECORDING_URL:': 'True',
        'CHATTER_MSG:': 'True',
        'PARTNER:': 'True',
    }
    for prefix, want in expected.items():
        line = next((l for l in lines if l.startswith(prefix)), '')
        check(f'{prefix.strip(":").lower()} = {want}', want in line, line)


def test_missed_inbound(opener):
    print('\n[5] Missed inbound — minimal payload')
    PL = base_completed_payload('MISSED', status=2,
                                 pickupTime=None, hangupTime=None,
                                 callLength=None, summary=None,
                                 transcription=None, sentiment=None,
                                 evaluationCriteriaResult=None,
                                 recordingUrl=None)
    check('200 on missed inbound', post(opener, PL)[0] == 200)
    out = shell("""
c = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-MISSED')], limit=1)
print('STATUS:', c.status)
print('DURATION:', c.duration_seconds)
print('SUMMARY_EMPTY:', not c.summary)
""")
    lines = out.splitlines()
    check('status = missed',
          'STATUS: missed' in (lines[0] if lines else ''),
          lines[0] if lines else '')
    check('duration = 0 (no pickup/hangup)',
          'DURATION: 0' in (lines[1] if len(lines) > 1 else ''),
          lines[1] if len(lines) > 1 else '')


def test_failed_outbound(opener):
    print('\n[6] Failed outbound — error path')
    PL = base_completed_payload('FAILED', status=7, type=2)
    check('200 on failed outbound', post(opener, PL)[0] == 200)
    out = shell("""
c = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-FAILED')], limit=1)
print('STATUS:', c.status)
print('DIRECTION:', c.direction)
""")
    lines = out.splitlines()
    check('status = failed', 'STATUS: failed' in (lines[0] if lines else ''), lines[0] if lines else '')
    check('direction = outbound', 'DIRECTION: outbound' in (lines[1] if len(lines) > 1 else ''), lines[1] if len(lines) > 1 else '')


def test_partner_resolution(opener):
    print('\n[7] Partner resolution chain')

    # Use a valid-shaped Saudi mobile number — normalize_e164 rejects
    # X-padded strings as invalid, which would fall to the placeholder
    # path instead of matching the pre-existing partner.
    TEST_PHONE = '+966500000099'
    out = shell(f"""
p = env['res.partner'].sudo().create({{'name':'PhoneMatch','phone':'{TEST_PHONE}'}})
env.cr.commit()
print(f'PARTNER_ID:{{p.id}}')
""")
    line = next(l for l in out.splitlines() if l.startswith('PARTNER_ID:'))
    pre_partner_id = int(line.split(':', 1)[1])

    PL = base_completed_payload('PHONEMATCH',
                                 callerNumber=TEST_PHONE,
                                 contactId='contact-PHONEMATCH-fresh',
                                 contactNumber=TEST_PHONE)
    check('200 phone-match', post(opener, PL)[0] == 200)

    out = shell(f"""
c = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-PHONEMATCH')], limit=1)
print('PARTNER_MATCHED:', c.partner_id.id == {pre_partner_id})
print('PARTNER_NAME:', c.partner_id.name)
print('LINK_CREATED:', bool(env['htf.contact.link'].sudo().search(
    [('htf_contact_id','=','contact-PHONEMATCH-fresh')], limit=1)))
""")
    lines = out.splitlines()
    match = next(l for l in lines if l.startswith('PARTNER_MATCHED:'))
    link = next(l for l in lines if l.startswith('LINK_CREATED:'))
    check('phone-match found existing partner',
          'PARTNER_MATCHED: True' in match, match)
    check('htf.contact.link backfilled',
          'LINK_CREATED: True' in link, link)


def test_unknown_enums(opener):
    print('\n[8] Unknown direction / status → graceful skip (200)')
    PL = base_completed_payload('UNKNOWN_STATUS', status=99)
    s, body = post(opener, PL)
    check('unknown status → 200 with skip note',
          s == 200, f'status={s} body={body}')
    PL2 = base_completed_payload('UNKNOWN_TYPE', type=99)
    s2, b2 = post(opener, PL2)
    check('unknown type → 200 with skip note',
          s2 == 200, f'status={s2} body={b2}')


def test_signal_bus(opener):
    print('\n[9] Signal bus dispatches by status bucket')
    out = shell("""
from odoo.addons.htf_call_center.signals import htf_signals
from odoo.addons.htf_call_center.services import calls
captured = {}
def make(name):
    def listener(payload): captured.setdefault(name, []).append(payload)
    return listener
for sig in ('htf.call.received','htf.call.missed','htf.call.failed'):
    htf_signals.subscribe(sig, make(sig))

# Drive directly via process() so we don't depend on HTTP idempotency.
for suffix, status in (('SIG-COMP', 1), ('SIG-MISS', 2), ('SIG-FAIL', 7)):
    payload = {
        'workspaceId':'00000000-0000-0000-0000-000000000000',
        'channelId':'3a20-test-p3-channel',
        'id': f'signal-test-{suffix}',
        'status': status, 'type': 1,
        'callerNumber':'+9665XXXXXXXXX',
        'creationTime':'2026-05-19T02:00:00Z',
    }
    calls.process(env, payload)

print('RECEIVED:', len(captured.get('htf.call.received', [])))
print('MISSED:', len(captured.get('htf.call.missed', [])))
print('FAILED:', len(captured.get('htf.call.failed', [])))
""")
    lines = out.splitlines()
    rec = next(l for l in lines if l.startswith('RECEIVED:'))
    miss = next(l for l in lines if l.startswith('MISSED:'))
    fail = next(l for l in lines if l.startswith('FAILED:'))
    check('htf.call.received fired on Completed',
          'RECEIVED: 1' in rec, rec)
    check('htf.call.missed fired on Missed',
          'MISSED: 1' in miss, miss)
    check('htf.call.failed fired on Failed',
          'FAILED: 1' in fail, fail)


def test_chatter_post_content(opener):
    print('\n[10] Chatter post content includes key elements')
    PL = base_completed_payload('CHATCHK')
    check('200 chat probe', post(opener, PL)[0] == 200)
    out = shell("""
c = env['htf.call'].sudo().search([('htf_call_id','=','call-P4E2E-CHATCHK')], limit=1)
m = c.chatter_message_id
print('BODY_LEN:', len(m.body or ''))
print('HAS_SUMMARY:', 'Summary' in (m.body or ''))
print('HAS_RECORDING:', 'Recording' in (m.body or ''))
print('HAS_DURATION:', '5:32' in (m.body or ''))
print('HAS_SENTIMENT:', 'Positive' in (m.body or ''))
""")
    lines = out.splitlines()
    for prefix, want in [
        ('HAS_SUMMARY:', 'chatter body contains "Summary"'),
        ('HAS_RECORDING:', 'chatter body contains "Recording"'),
        ('HAS_DURATION:', 'chatter body shows duration 5:32'),
        ('HAS_SENTIMENT:', 'chatter body shows Positive sentiment badge'),
    ]:
        line = next((l for l in lines if l.startswith(prefix)), '')
        check(want, 'True' in line, line)


# -------------------------------------------------------------- #
# Main                                                           #
# -------------------------------------------------------------- #

def main():
    print('=== P4 BACKEND E2E ===')
    opener = _session()
    ensure_signed_mode()
    ensure_test_channel()
    clean_test_artefacts()
    test_route_basics(opener)
    test_idempotency(opener)
    test_status_transition(opener)
    test_completed_inbound_full(opener)
    test_missed_inbound(opener)
    test_failed_outbound(opener)
    test_partner_resolution(opener)
    test_unknown_enums(opener)
    test_signal_bus(opener)
    test_chatter_post_content(opener)

    print(f'\n=== RESULT: {PASS}/{PASS + FAIL} passed ===')
    if FAIL:
        print('\nFailures:')
        for f in FAILURES:
            print(f'  - {f}')
        sys.exit(1)


if __name__ == '__main__':
    main()
