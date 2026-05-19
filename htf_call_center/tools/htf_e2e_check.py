"""Comprehensive E2E smoke test of htf_call_center against the local Odoo.

Drives the full module via JSON-RPC (same path a real browser uses), so any
field, view, button, or model-method that breaks at runtime fails here.

Pass criteria:
  every named check returns ✓; the script exits 0 if all green, 1 if any red.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import urllib.request as ur

URL = "http://localhost:8069"
DB = "odoo"
LOGIN = "admin"
PASSWORD = "admin"

# ---------------------------------------------------------------------------
# Tiny JSON-RPC client
# ---------------------------------------------------------------------------

def _post(path: str, payload: dict, cookie: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    req = ur.Request(f"{URL}{path}", data=json.dumps(payload).encode(), headers=headers)
    with ur.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read())
        set_cookie = resp.headers.get("Set-Cookie", "")
        return body, set_cookie

def login() -> str:
    body, sc = _post("/web/session/authenticate", {
        "jsonrpc": "2.0",
        "params": {"db": DB, "login": LOGIN, "password": PASSWORD},
    })
    if not body.get("result", {}).get("uid"):
        raise SystemExit(f"login failed: {body}")
    return sc.split(";")[0]

COOKIE = login()

def kw(model: str, method: str, args=(), kwargs=None):
    body, _ = _post("/web/dataset/call_kw", {
        "jsonrpc": "2.0",
        "params": {"model": model, "method": method, "args": list(args), "kwargs": kwargs or {}},
    }, cookie=COOKIE)
    if "error" in body:
        return ("ERR", body["error"]["data"].get("message", body["error"].get("message")))
    return body.get("result")

# ---------------------------------------------------------------------------
# Check harness
# ---------------------------------------------------------------------------

CHECKS: list[tuple[str, bool, str]] = []  # (name, ok, detail)

def check(name: str, ok: bool, detail="") -> None:
    detail_str = str(detail) if not isinstance(detail, str) else detail
    CHECKS.append((name, ok, detail_str))
    icon = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {icon} {name}{(' — ' + detail_str) if detail_str else ''}")

def _odoo_shell(code: str) -> str:
    """Execute a Python snippet inside the running Odoo process.

    `odoo shell` reads stdin as a script; results we want to assert get
    printed and parsed by the caller. Avoids the `ModuleNotFoundError:
    odoo.addons.htf_call_center` you get from a bare `python3` invocation
    because odoo.addons is a namespace package set up by Odoo's bootstrap.
    """
    out = subprocess.run(
        ["docker", "exec", "-i", "odoo-app",
         "odoo", "shell", "-d", DB, "--no-http", "--log-level=warn"],
        input=code, capture_output=True, text=True, timeout=60,
    )
    return out.stdout + out.stderr

# ---------------------------------------------------------------------------
# 1. Module state
# ---------------------------------------------------------------------------
print("\n— Module state")
mod = kw("ir.module.module", "search_read",
         [[["name", "=", "htf_call_center"]]],
         {"fields": ["name", "state", "latest_version"]})
check("module installed", bool(mod) and mod[0]["state"] == "installed",
      f"state={mod[0]['state']!r} v={mod[0]['latest_version']!r}" if mod else "not found")

# ---------------------------------------------------------------------------
# 2. Models registered
# ---------------------------------------------------------------------------
print("\n— Models")
models_in_db = kw("ir.model", "search_read",
                  [[["model", "in", ["htf.config", "htf.webhook.event"]]]],
                  {"fields": ["model"]})
present = {m["model"] for m in (models_in_db or [])}
check("htf.config registered (AbstractModel)", "htf.config" in present)
check("htf.webhook.event registered", "htf.webhook.event" in present)

# ---------------------------------------------------------------------------
# 3. Menu structure
# ---------------------------------------------------------------------------
print("\n— Menus")
menus = kw("ir.ui.menu", "search_read",
           [[["name", "ilike", "Hatif"]]],
           {"fields": ["name", "complete_name"]})
names = [m["complete_name"] for m in (menus or [])]
check("Hatif root menu", any(n == "Hatif" for n in names), f"saw {names}")
# Webhook events submenu may be lazy-loaded; check by xmlid:
ref = kw("ir.model.data", "search_read",
         [[["module", "=", "htf_call_center"], ["name", "=", "menu_htf_webhook_events"]]],
         {"fields": ["res_id"]})
check("Webhook Events submenu present", bool(ref))

# ---------------------------------------------------------------------------
# 4. Settings form arch — every block + every field must be in the XML
# ---------------------------------------------------------------------------
print("\n— Settings form (res.config.settings)")
view = kw("res.config.settings", "get_view", (), {"view_type": "form"})
arch = view["arch"] if view and isinstance(view, dict) else ""
check("settings form loads", bool(arch), f"{len(arch)} chars")
required_blocks = [
    "Connection", "Webhook signing", "Polling", "Defaults", "Debug",
]
for b in required_blocks:
    check(f"settings block '{b}' present", b in arch)
required_fields = [
    "htf_client_id", "htf_client_secret", "htf_base_url", "htf_scope",
    "htf_webhook_secret_current", "htf_webhook_secret_previous",
    "htf_poll_contacts_interval_min", "htf_poll_conversations_interval_min",
    "htf_default_voice", "htf_timezone_offset_for_filters",
    "htf_debug_log_enabled", "htf_dev_mode_skip_hmac",
]
for f in required_fields:
    check(f"settings field {f} present", f in arch)
check("Test Connection button wired", 'action_test_connection' in arch)
# Settings LEFT-RAIL tab visibility: needs `name=` (NOT `data-key=`) on
# <app>. data-key compiles the arch but the tab silently doesn't appear.
import re as _re
_app_names = _re.findall(r'<app[^>]*name="([^"]+)"', arch)
check("Hatif tab actually registered in Settings left rail",
      'htf_call_center' in _app_names,
      f"<app name=...> entries: {_app_names}")

# ---------------------------------------------------------------------------
# 5. htf.config param round-trip — every parameter persists with right type
# ---------------------------------------------------------------------------
print("\n— htf.config params (typed accessors)")
def roundtrip(key, value, expected):
    kw("htf.config", "set_param", (key, value))
    got = kw("htf.config", "get_param", (key,))
    return got == expected, f"set={value!r} got={got!r} expected={expected!r}"

ok, d = roundtrip("base_url", "https://api.example.test", "https://api.example.test")
check("string param set/get", ok, d)
ok, d = roundtrip("poll_contacts_interval_min", 45, 45)
check("int param coerces from str storage", ok, d)
ok, d = roundtrip("debug_log_enabled", True, True)
check("bool param True", ok, d)
ok, d = roundtrip("debug_log_enabled", False, False)
check("bool param False", ok, d)
# restore
kw("htf.config", "set_param", ("base_url", "https://api.voxa.sa"))
kw("htf.config", "set_param", ("poll_contacts_interval_min", 30))

# Unknown param raises HtfConfigError (surfaces as Odoo error)
res = kw("htf.config", "get_param", ("nonexistent_thing",))
check("unknown param raises", isinstance(res, tuple) and res[0] == "ERR", str(res))

# ---------------------------------------------------------------------------
# 6. Webhook secrets
# ---------------------------------------------------------------------------
print("\n— Webhook secrets (rotation overlap support)")
kw("htf.config", "set_param", ("webhook_secret_current", "secret-A"))
kw("htf.config", "set_param", ("webhook_secret_previous", ""))
res = kw("htf.config", "webhook_secrets")
check("only current returned when previous empty", res == ["secret-A"], str(res))
kw("htf.config", "set_param", ("webhook_secret_previous", "secret-B"))
res = kw("htf.config", "webhook_secrets")
check("both returned during overlap", res == ["secret-A", "secret-B"], str(res))
kw("htf.config", "set_param", ("webhook_secret_current", ""))
kw("htf.config", "set_param", ("webhook_secret_previous", ""))

# ---------------------------------------------------------------------------
# 7. Test Connection button — error paths
# ---------------------------------------------------------------------------
print("\n— action_test_connection error paths")
kw("htf.config", "set_param", ("client_id", ""))
kw("htf.config", "set_param", ("client_secret", ""))
res = kw("htf.config", "action_test_connection")
ok = isinstance(res, tuple) and res[0] == "ERR" and "client_id" in res[1]
check("no creds → 'Set client_id and client_secret first'", ok, str(res))

kw("htf.config", "set_param", ("client_id", "bogus"))
kw("htf.config", "set_param", ("client_secret", "bogus"))
res = kw("htf.config", "action_test_connection")
ok = isinstance(res, tuple) and res[0] == "ERR" and "Hatif" in res[1] and ("401" in res[1] or "rejected" in res[1] or "Could not reach" in res[1])
check("bogus creds → propagates Hatif rejection", ok, str(res))
kw("htf.config", "set_param", ("client_id", ""))
kw("htf.config", "set_param", ("client_secret", ""))

# ---------------------------------------------------------------------------
# 8. Webhook event idempotency
# ---------------------------------------------------------------------------
print("\n— htf.webhook.event idempotency")
# clean slate
kw("htf.webhook.event", "search_read", [[["event_id", "ilike", "e2e-"]]], {"fields": ["id"]})

# Note: record_or_skip takes bytes for raw_body, JSON-RPC can't send bytes,
# call without it (server signature allows empty bytes default).
r1 = kw("htf.webhook.event", "record_or_skip", ("e2e-evt-1", "whatsapp"))
check("first delivery creates row", isinstance(r1, list) and len(r1) == 1, str(r1))

r2 = kw("htf.webhook.event", "record_or_skip", ("e2e-evt-1", "whatsapp"))
check("duplicate returns False (no second row)", r2 is False, str(r2))

# Same event_id different route allowed
r3 = kw("htf.webhook.event", "record_or_skip", ("e2e-evt-1", "call"))
check("same event_id different route OK", isinstance(r3, list) and len(r3) == 1, str(r3))

# Missing fields returns empty recordset
r4 = kw("htf.webhook.event", "record_or_skip", ("", "whatsapp"))
check("empty event_id returns empty recordset", r4 == [], str(r4))

# mark_processed
if isinstance(r1, list):
    kw("htf.webhook.event", "mark_processed", (r1[0], "e2e test"))
    rec = kw("htf.webhook.event", "read", (r1, ["processed", "note"]))
    check("mark_processed sets flag + note", rec and rec[0]["processed"] and rec[0]["note"] == "e2e test", str(rec))

# Cleanup
to_kill = kw("htf.webhook.event", "search", [[["event_id", "ilike", "e2e-"]]])
if to_kill:
    kw("htf.webhook.event", "unlink", (to_kill,))

# ---------------------------------------------------------------------------
# 9. Crons exist + are active + interval correct
# ---------------------------------------------------------------------------
print("\n— Scheduled crons")
crons = kw("ir.cron", "search_read",
           [[["name", "ilike", "HTF:"]]],
           {"fields": ["name", "active", "interval_number", "interval_type"]})
by_name = {c["name"]: c for c in (crons or [])}
c = by_name.get("HTF: refresh OAuth token")
check("token-refresh cron exists, active, 30m", bool(c) and c["active"] and c["interval_number"] == 30 and c["interval_type"] == "minutes",
      str(c))
c = by_name.get("HTF: purge old webhook events")
check("purge cron exists, active, 1d", bool(c) and c["active"] and c["interval_number"] == 1 and c["interval_type"] == "days",
      str(c))

# Calling cron entry points should not raise — both are no-op when no token/event
res = kw("htf.config", "cron_refresh_token")
check("cron_refresh_token callable (no-op without token)", res is None or res is False, str(res))
res = kw("htf.webhook.event", "cron_purge_old", (90,))
check("cron_purge_old callable", isinstance(res, int), str(res))

# ---------------------------------------------------------------------------
# 10. Security groups + ACL + record rules exist
# ---------------------------------------------------------------------------
print("\n— Security")
g_user = kw("ir.model.data", "search_read",
            [[["module", "=", "htf_call_center"], ["name", "=", "group_user"]]],
            {"fields": ["res_id"]})
g_admin = kw("ir.model.data", "search_read",
             [[["module", "=", "htf_call_center"], ["name", "=", "group_admin"]]],
             {"fields": ["res_id"]})
check("group_user exists", bool(g_user))
check("group_admin exists", bool(g_admin))
acl = kw("ir.model.access", "search_read",
         [[["name", "ilike", "htf.webhook.event"]]],
         {"fields": ["name", "perm_read", "perm_write"]})
check("ACL rows on htf.webhook.event", len(acl or []) >= 2, f"{len(acl or [])} rows")
rules = kw("ir.rule", "search_read",
           [[["name", "ilike", "htf.webhook.event"]]],
           {"fields": ["name"]})
check("Record rules on htf.webhook.event", len(rules or []) >= 2, f"{len(rules or [])} rules")

# ---------------------------------------------------------------------------
# 11. HMAC verifier (inside the container, since it's a pure python helper)
# ---------------------------------------------------------------------------
print("\n— HMAC verifier (in-container exec)")
import subprocess
body = b'{"hello":"world"}'
sig = hmac.new(b"secret-A", body, hashlib.sha256).hexdigest()
output = _odoo_shell(f'''
from odoo.addons.htf_call_center.services import hmac_verify
print("VALID",    hmac_verify.verify({body!r}, "{sig}",     ["secret-A"]))
print("INVALID",  hmac_verify.verify({body!r}, "deadbeef",  ["secret-A"]))
print("NOSIG",    hmac_verify.verify({body!r}, "",          ["secret-A"]))
print("ROTATION", hmac_verify.verify({body!r}, "{sig}",     ["other", "secret-A"]))
print("NOSEC",    hmac_verify.verify({body!r}, "{sig}",     []))
''')
check("HMAC valid sig → True", "VALID True" in output, "")
check("HMAC invalid sig → False", "INVALID False" in output, "")
check("HMAC empty sig → False", "NOSIG False" in output, "")
check("HMAC accepts during rotation overlap", "ROTATION True" in output, "")
check("HMAC empty secret list → False", "NOSEC False" in output, "")

# ---------------------------------------------------------------------------
# 12. Signal bus (in-container)
# ---------------------------------------------------------------------------
print("\n— Signal bus")
output = _odoo_shell('''
from odoo.addons.htf_call_center.signals import htf_signals
seen = []
def cb(p): seen.append(p)
htf_signals.subscribe("e2e.test.bus", cb)
htf_signals.fire("e2e.test.bus", {"k": "v"})
htf_signals.unsubscribe("e2e.test.bus", cb)
htf_signals.fire("e2e.test.bus", {"k": "v2"})
print("RESULT", seen)
''')
check("signal subscribe/fire/unsubscribe", "RESULT [{'k': 'v'}]" in output, "")

# ---------------------------------------------------------------------------
# 13. Log redaction (in-container)
# ---------------------------------------------------------------------------
print("\n— Log redaction filter")
output = _odoo_shell('''
import logging
from odoo.addons.htf_call_center.log_redaction import HtfSecretRedactionFilter
flt = HtfSecretRedactionFilter()
rec = logging.LogRecord("t", logging.INFO, "", 0, "Authorization: Bearer eyJabc.tok123", None, None)
flt.filter(rec)
print("BEARER", "eyJabc" not in rec.msg, repr(rec.msg))
rec = logging.LogRecord("t", logging.INFO, "", 0, "webhook_secret_current=top_secret", None, None)
flt.filter(rec)
print("SECRET", "top_secret" not in rec.msg, repr(rec.msg))
''')
check("redacts bearer token", "BEARER True" in output, "")
check("redacts webhook secret kv", "SECRET True" in output, "")

# ---------------------------------------------------------------------------
# 14. Service factory — auth + http both instantiate
# ---------------------------------------------------------------------------
print("\n— Service factory")
output = _odoo_shell('''
auth = env["htf.config"].get_service("auth")
http = env["htf.config"].get_service("http")
print("AUTH", auth.__class__.__name__, "HTTP", http.__class__.__name__)
try:
    env["htf.config"].get_service("nonexistent")
    print("UNKNOWN no_raise")
except Exception as exc:
    print("UNKNOWN raised", exc.__class__.__name__)
''')
check("get_service('auth') returns AuthService", "AUTH AuthService" in output, "")
check("get_service('http') returns HtfHttpClient", "HTTP HtfHttpClient" in output, "")
check("get_service('nonexistent') raises", "UNKNOWN raised" in output, "")

# ---------------------------------------------------------------------------
# 15. Public-surface boundary (constants / exceptions / signals importable
#     without touching internals)
# ---------------------------------------------------------------------------
print("\n— Public API surface (bridge consumers)")
output = _odoo_shell('''
from odoo.addons.htf_call_center import constants, exceptions, signals
from odoo.addons.htf_call_center.constants import (
    WEBHOOK_SIGNATURE_HEADER, WEBHOOK_HASH_ALGO,
    RETRY_BUDGET, TOKEN_REFRESH_LEEWAY_SECONDS,
    DNC_KEYWORDS_DEFAULT, SUPPORTED_LANGUAGES,
)
from odoo.addons.htf_call_center.exceptions import (
    HtfApiError, HtfAuthenticationError, HtfRateLimitError,
    HtfDncBlockedError, HtfWindowExpiredError, HtfChannelNotFoundError,
)
from odoo.addons.htf_call_center.signals import htf_signals
print("PUBLIC_OK", constants.WEBHOOK_SIGNATURE_HEADER, constants.WEBHOOK_HASH_ALGO)
''')
check("constants + exceptions + signals importable as a stable public surface",
      "PUBLIC_OK X-Voxa-Signature sha256" in output, "")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(1 for _, ok, _ in CHECKS if ok)
total = len(CHECKS)
failed = [(n, d) for n, ok, d in CHECKS if not ok]
print(f"\n{'='*60}")
print(f"  {passed}/{total} passed")
if failed:
    print(f"\nFailed:")
    for n, d in failed:
        print(f"  ✗ {n}\n      {d}")
print(f"{'='*60}")
sys.exit(0 if passed == total else 1)
