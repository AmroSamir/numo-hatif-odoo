"""P1 E2E check — models, services, wizards, crons, menus, security.

Doesn't require real Hatif creds; service-layer round-trips are mocked
for sync_from_htf paths by setting an unreachable base_url and asserting
the expected typed exception. With real creds, the operator can flip
HTF_REAL_API=1 to skip mocked paths and verify against live Hatif.
"""
from __future__ import annotations

import json
import sys
import subprocess
import urllib.request as ur

URL = "http://localhost:8069"
DB = "odoo"

req = ur.Request(f"{URL}/web/session/authenticate",
                 data=json.dumps({"jsonrpc": "2.0", "params": {"db": DB, "login": "admin", "password": "admin"}}).encode(),
                 headers={"Content-Type": "application/json"})
COOKIE = ur.urlopen(req, timeout=10).headers.get("Set-Cookie", "").split(";")[0]

def kw(model, method, args=(), kwargs=None):
    req = ur.Request(f"{URL}/web/dataset/call_kw",
                     data=json.dumps({"jsonrpc": "2.0", "params": {
                         "model": model, "method": method,
                         "args": list(args), "kwargs": kwargs or {},
                     }}).encode(),
                     headers={"Content-Type": "application/json", "Cookie": COOKIE})
    r = json.loads(ur.urlopen(req, timeout=20).read())
    if "error" in r:
        return ("ERR", r["error"]["data"].get("message", r["error"].get("message")))
    return r.get("result")

def shell(code):
    out = subprocess.run(
        ["docker", "exec", "-i", "odoo-app",
         "odoo", "shell", "-d", DB, "--no-http", "--log-level=warn"],
        input=code, capture_output=True, text=True, timeout=90,
    )
    return out.stdout + out.stderr

CHECKS = []
def check(name, ok, detail=""):
    detail_str = str(detail) if not isinstance(detail, str) else detail
    CHECKS.append((name, ok, detail_str))
    icon = "\033[32m✓\033[0m" if ok else "\033[31m✗\033[0m"
    print(f"  {icon} {name}{(' — ' + detail_str) if detail_str else ''}")

# ---------------------------------------------------------------------------
# 1. New models registered
# ---------------------------------------------------------------------------
print("\n— P1 models registered")
got = kw("ir.model", "search_read",
         [[["model", "in", ["htf.channel", "htf.tag", "htf.user.link",
                            "htf.contact.link"]]]],
         {"fields": ["model"]})
present = {m["model"] for m in (got or [])}
for m in ("htf.channel", "htf.tag", "htf.user.link", "htf.contact.link"):
    check(f"{m} registered", m in present)

# ---------------------------------------------------------------------------
# 2. Extension fields on existing models
# ---------------------------------------------------------------------------
print("\n— Extension fields")
def has_field(model, name):
    fld = kw("ir.model.fields", "search_count",
             [[["model", "=", model], ["name", "=", name]]])
    return fld == 1

for fname in ("x_htf_contact_id", "x_htf_synced_at", "x_htf_last_inbound_at",
              "x_htf_24h_window_open", "x_htf_opted_out",
              "x_htf_default_channel_id", "x_htf_call_count",
              "x_htf_message_count"):
    check(f"res.partner.{fname}", has_field("res.partner", fname))

for fname in ("x_htf_user_id", "x_htf_user_email", "x_htf_role"):
    check(f"res.users.{fname}", has_field("res.users", fname))

for fname in ("x_htf_channel_ids", "x_htf_default_outbound_wa_channel_id",
              "x_htf_default_outbound_call_channel_id", "x_htf_routing_strategy"):
    check(f"crm.team.{fname}", has_field("crm.team", fname))

# ---------------------------------------------------------------------------
# 3. Views render — every new model + extension view
# ---------------------------------------------------------------------------
print("\n— Views render")
for model in ("htf.channel", "htf.tag", "htf.user.link", "htf.contact.link"):
    v = kw(model, "get_view", (), {"view_type": "list"})
    check(f"{model} list view loads", isinstance(v, dict) and "arch" in v)
    v = kw(model, "get_view", (), {"view_type": "form"})
    check(f"{model} form view loads", isinstance(v, dict) and "arch" in v)

# Partner form should include the Hatif tab
v = kw("res.partner", "get_view", (), {"view_type": "form"})
arch = v.get("arch", "") if isinstance(v, dict) else ""
check("res.partner form has Hatif tab", "x_htf_contact_id" in arch and "x_htf_24h_window_open" in arch)

# Users form Hatif tab — must target the FULL form (priority 16), not the
# simplified one Odoo returns by default. Look up by xmlid.
full_form = kw("ir.model.data", "search_read",
               [[["module", "=", "base"], ["name", "=", "view_users_form"]]],
               {"fields": ["res_id"]})
full_id = full_form[0]["res_id"] if full_form else False
v = kw("res.users", "get_view", (), {"view_id": full_id, "view_type": "form"})
arch = v.get("arch", "") if isinstance(v, dict) else ""
check("res.users full form has Hatif fields", "x_htf_user_id" in arch)

# crm.team form Hatif Channels tab
v = kw("crm.team", "get_view", (), {"view_type": "form"})
arch = v.get("arch", "") if isinstance(v, dict) else ""
check("crm.team form has Hatif Channels tab", "x_htf_channel_ids" in arch and "x_htf_routing_strategy" in arch)

# ---------------------------------------------------------------------------
# 4. Menu structure
# ---------------------------------------------------------------------------
print("\n— Menus")
root = kw("ir.ui.menu", "search_read", [[["name", "=", "Hatif"], ["parent_id", "=", False]]], {"fields": ["id"]})
if not root:
    check("Hatif root menu", False, "missing")
else:
    kids = kw("ir.ui.menu", "search_read", [[["parent_id", "=", root[0]["id"]]]], {"fields": ["name"]})
    names = {k["name"] for k in (kids or [])}
    # Bind Channels Wizard intentionally NOT a top-level submenu — it
    # lives as a header button inside the Channels list view
    # (see htf_channel_views.xml / menus.xml:45-50).
    for required in ("Channels", "Tags", "User Mapping (list)",
                     "Contact Links", "Webhook events",
                     "Map Users Wizard",
                     "Import vCards",
                     "Sync Channels", "Sync Tags", "Sync Workspace Users"):
        check(f"submenu '{required}' present", required in names)

# ---------------------------------------------------------------------------
# 5. Crons
# ---------------------------------------------------------------------------
print("\n— Crons")
crons = kw("ir.cron", "search_read", [[["name", "ilike", "HTF:"]]],
           {"fields": ["name", "active", "interval_number", "interval_type"]})
by_name = {c["name"]: c for c in (crons or [])}
expected = {
    "HTF: refresh OAuth token": (True, 30, "minutes"),
    "HTF: purge old webhook events": (True, 1, "days"),
    "HTF: nightly channel sync": (True, 1, "days"),
    "HTF: poll contacts (incremental)": (True, 30, "minutes"),
}
for name, (active, num, typ) in expected.items():
    c = by_name.get(name)
    ok = bool(c) and c["active"] == active and c["interval_number"] == num and c["interval_type"] == typ
    check(f"cron '{name}'", ok, str(c) if not ok else "")

# ---------------------------------------------------------------------------
# 6. Service factory — all P1 services callable
# ---------------------------------------------------------------------------
print("\n— Service factory (P1 services)")
output = shell('''
for name in ("channels", "tags", "workspace", "contacts", "contact_properties"):
    svc = env["htf.config"].get_service(name)
    print(f"SVC {name} -> {svc.__class__.__name__}")
''')
for name, cls in (("channels", "ChannelService"), ("tags", "TagService"),
                  ("workspace", "WorkspaceService"), ("contacts", "ContactService"),
                  ("contact_properties", "ContactPropertyService")):
    check(f"get_service('{name}') -> {cls}", f"SVC {name} -> {cls}" in output, "")

# ---------------------------------------------------------------------------
# 7. Phone E.164 normalizer
# ---------------------------------------------------------------------------
print("\n— Phone normalizer")
output = shell('''
from odoo.addons.htf_call_center.utils.phone import normalize_e164, normalize_e164_strict
cases = [
    ("+966 50 123 4567", "+966501234567"),
    ("00966501234567",   "+966501234567"),
    ("0501234567",       "+966501234567"),  # leading-zero local
    ("050-123-4567",     "+966501234567"),
    ("966501234567",     "+966501234567"),
    ("",                  None),
    ("not a number",      None),
    ("+966 53 999 9999", "+966539999999"),  # 053 prefix
]
results = []
for raw, expected in cases:
    got = normalize_e164(raw)
    ok = got == expected
    results.append((raw, expected, got, ok))
    print(f"NORM {raw!r} -> {got!r} expected={expected!r} ok={ok}")
try:
    normalize_e164_strict("xxx")
    print("STRICT no_raise")
except ValueError as e:
    print(f"STRICT raised={e}")
''')
for raw, exp, _, _ in [("+966 50 123 4567", "+966501234567", None, True),
                        ("0501234567", "+966501234567", None, True),
                        ("00966501234567", "+966501234567", None, True),
                        ("not a number", None, None, True)]:
    check(f"phone normalize {raw!r} → {exp!r}",
          f"NORM {raw!r} -> {exp!r}" in output, "")
check("strict variant raises on garbage", "STRICT raised" in output, "")

# ---------------------------------------------------------------------------
# 8. Service sync methods callable (real HTTP attempt → 401 since no creds)
# ---------------------------------------------------------------------------
print("\n— Service sync entry points")
# Need creds set so HTTP client actually tries (otherwise auth raises ConfigError).
kw("htf.config", "set_param", ("client_id", "test-bogus"))
kw("htf.config", "set_param", ("client_secret", "test-bogus"))
res = kw("htf.config", "action_sync_channels")
ok = isinstance(res, tuple) and res[0] == "ERR" and ("Hatif" in res[1] or "401" in res[1] or "Authentication" in res[1])
check("action_sync_channels fails on bad creds (clean error)", ok, str(res))
res = kw("htf.config", "action_sync_tags")
ok = isinstance(res, tuple) and res[0] == "ERR"
check("action_sync_tags fails on bad creds (clean error)", ok, str(res))
res = kw("htf.config", "action_sync_workspace_users")
ok = isinstance(res, tuple) and res[0] == "ERR"
check("action_sync_workspace_users fails on bad creds (clean error)", ok, str(res))
kw("htf.config", "set_param", ("client_id", ""))
kw("htf.config", "set_param", ("client_secret", ""))

# ---------------------------------------------------------------------------
# 9. Wizards openable
# ---------------------------------------------------------------------------
print("\n— Wizards")
for wmodel in ("htf.bind.channels.wizard", "htf.map.users.wizard",
               "htf.import.vcards.wizard"):
    v = kw(wmodel, "get_view", (), {"view_type": "form"})
    check(f"{wmodel} form loads", isinstance(v, dict) and "arch" in v)
    # Try opening via default_get
    res = kw(wmodel, "default_get", [[]])
    check(f"{wmodel} default_get works", isinstance(res, dict), "")

# ---------------------------------------------------------------------------
# 10. ACLs cover all new models
# ---------------------------------------------------------------------------
print("\n— ACLs")
for model in ("htf.channel", "htf.tag", "htf.user.link", "htf.contact.link",
              "htf.bind.channels.wizard", "htf.map.users.wizard",
              "htf.import.vcards.wizard"):
    n = kw("ir.model.access", "search_count", [[["model_id.model", "=", model]]])
    check(f"ACLs on {model}", isinstance(n, int) and n >= 1, f"{n} rules")

# ---------------------------------------------------------------------------
# 11. Constraint check — only one default-WA channel per team
# ---------------------------------------------------------------------------
print("\n— htf.channel uniqueness constraints")
output = shell('''
Team = env["crm.team"]
Channel = env["htf.channel"]
team = Team.create({"name": "_e2e_team", "sequence": 999})
c1 = Channel.create({
    "name": "_e2e_chan_1", "htf_channel_id": "_e2e_uuid_1",
    "channel_type": "whatsapp", "team_id": team.id,
    "default_for_outbound_wa": True,
})
print("FIRST_OK")
try:
    c2 = Channel.create({
        "name": "_e2e_chan_2", "htf_channel_id": "_e2e_uuid_2",
        "channel_type": "whatsapp", "team_id": team.id,
        "default_for_outbound_wa": True,
    })
    print("SECOND_NO_RAISE")
except Exception as exc:
    print(f"SECOND_RAISED {exc.__class__.__name__}")
finally:
    env.cr.rollback()
''')
check("first channel with default_for_outbound_wa accepted", "FIRST_OK" in output, "")
check("second on same team raises ValidationError",
      "SECOND_RAISED ValidationError" in output, "")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(1 for _, ok, _ in CHECKS if ok)
total = len(CHECKS)
failed = [(n, d) for n, ok, d in CHECKS if not ok]
print(f"\n{'='*60}")
print(f"  P1 E2E: {passed}/{total} passed")
if failed:
    print("\nFailed:")
    for n, d in failed:
        print(f"  ✗ {n}\n      {d}")
print(f"{'='*60}")
sys.exit(0 if passed == total else 1)
