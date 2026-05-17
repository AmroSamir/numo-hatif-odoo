# NEXT SESSION — start here

Last updated: 2026-05-17 (end of session that shipped P0 + P1).

Read this BEFORE doing anything else when you (next Claude Code session)
open this repo. It tells you where we are, what's verified, what to
build next, and the workflow rules Amr expects.

---

## 1. Read THE DRILL first

`/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md` opens with **THE DRILL**.
It is non-negotiable. Summary:

1. Edit → re-read file to confirm change actually landed
2. Upgrade module via `docker exec odoo-app odoo -d test -u <module> --stop-after-init --log-level=warn`
3. Restart container — `--dev=reload` on macOS/OrbStack doesn't always pick up changes
4. **Exercise the actual feature path** via `odoo shell` or JSON-RPC — NOT just "tests pass"
5. Verify the user-visible goal is met (not just "it installs")
6. Only THEN ask Amr to verify in his browser. Report includes proof.
7. Push to GitHub once Amr signs off

The DRILL also has 17+ Odoo-19 footguns logged. Re-read them before
touching XML, security, fields, or wizards.

---

## 2. Where everything lives

| Thing | Location |
|---|---|
| GitHub repo (source of truth) | https://github.com/AmroSamir/numo-hatif-odoo |
| Local working dir | `~/numo-hatif-odoo` |
| Bind-mounted into container as | `/mnt/extra-addons/htf_call_center` + `/mnt/extra-addons/numo_crm_htf` |
| Docker compose file | `/Users/amro/Downloads/Claude/ai-dnd-builder/odoo-local/docker-compose.yml` |
| Local Odoo container | `odoo-app` (`odoo:19`), port 8069 |
| Local Postgres container | `odoo-db` (`postgres:15`) |
| Live dev DB | **`test`** (has BI + many core apps installed; admin login is Amr's email) |
| Empty starter DB | `odoo` (admin/admin works but only mail+contacts+htf are installed → no settings tabs render) |
| Planning docs | `htf_call_center/docs/planning/` (00_OVERVIEW.md, P0–P10 phase docs, SECURITY, DATA_MODEL, API_CONTRACT, SIGNAL_BUS, OPEN_QUESTIONS, RISK_REGISTER, STATUS) |
| E2E smoke suite (P0) | `/tmp/htf_e2e_check.py` — 59/59 green |
| E2E smoke suite (P1) | `/tmp/htf_p1_check.py` — 73/73 green |
| Project CLAUDE.md (THE DRILL) | `/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md` |

---

## 3. Status — what's shipped, verified, working

### P0 — Foundation (DONE, live-verified)

- `htf_call_center` module installable in Odoo 19
- Settings → Hatif tab renders with Connection / Webhook signing /
  Polling / Defaults / Debug / Sync from Hatif blocks
- OAuth `client_credentials` flow against `api.voxa.sa` working
  (Test Connection button → green toast)
- HMAC verifier ready for inbound webhooks (X-Voxa-Signature, raw-body,
  no timestamp window per Q-03 ANSWERED, rotation overlap supported)
- Signal bus (`htf_signals`) for in-process pub/sub
- Log redaction filter strips bearer tokens + webhook secrets
- `htf.webhook.event` idempotency table + nightly purge cron
- Token refresh cron every 30 min
- Pylint custom rule blocks bridge from importing vendor internals
- group_user + group_admin security groups (admin auto-assigned via
  `user_ids` on group_admin)

### P1 — Channels + Contacts + Users (DONE, live-UAT'd)

- 4 new models: `htf.channel`, `htf.tag`, `htf.user.link`, `htf.contact.link`
- Extensions on `res.partner` (8 fields incl. computed 24h-window),
  `res.users` (3 fields + SELF_READABLE_FIELDS), `crm.team` (One2many
  channels + computed defaults + routing strategy)
- 5 services: channels, tags, workspace, contacts, contact_properties
  (all idempotent, all defensive against Hatif's actual response shapes
  — `phoneNumber` is dict, `role` is int, channel type key is `type`)
- E.164 phone normalizer in `utils/phone.py` (KSA-aware)
- 3 wizards: Bind Channels, Map Users, Import vCards
- Sync buttons on Settings → Hatif (Channels primary, Tags + Workspace
  secondary). Server-action menus removed (don't render in Odoo 19 nav).
- 4 active crons: token refresh (30m), webhook purge (1d), channel
  sync (1d), contacts poll (30m, no-op until Q-10 follow-up)

### Live verification snapshot (against real Numo workspace, 2026-05-17)

```
=== Sync Channels ===
  [3a20ffce…] أكاديمية نمو      type=both  +966115001591  active
  [3a21006b…] الدعم الفني        type=both  +966115001592  active

=== Sync Workspace Users (7) ===
  سامي العنزي           sami@numo.sa                       OWNER
  الحسناء القحطاني      customerservice.diip@gmail.com     member
  شموس عبدالكريم        shomos@numo.sa                     member
  سامية                 samiah.alanizi@numo.sa             member
  ندى ال صبحان         nadamahdi.su@gmail.com             member
  نوره النويصر          customer.service.numo@gmail.com    member
  Riham                navhav66@gmail.com                 member

=== Sync Tags (1) ===
  مهتم (pinned)

=== Map Users Wizard ===
  Assigns user_id → htf.user.link.user_id persists, no validation error.
```

---

## 4. Next phase — P2 (WhatsApp Inbound)

Read `htf_call_center/docs/planning/P2_WHATSAPP_INBOUND.md` first.

### What P2 builds

- `htf.message` model (already defined in DATA_MODEL.md spec)
- Webhook controller at `POST /htf/webhook/whatsapp` with HMAC verify
  (use existing `services/hmac_verify.py`) + idempotency
  (`htf.webhook.event` already exists)
- `services/whatsapp_inbound.py` — dispatches text / image / video /
  audio / document / sticker / location / contact / template messages
- Auto-create `res.partner` for unknown phone numbers
- Post inbound bubble to partner chatter
- Update `partner.x_htf_last_inbound_at` (24h window field already
  computed)
- Fire `htf.wa.inbound` signal (already documented in SIGNAL_BUS.md)
- Handle outbound STATUS updates (delivered/read/failed) coming in via
  the same endpoint — update existing `htf.message` row, refresh
  chatter status icons

### Blockers Amr needs to answer first

Q-05 (single vs per-brand workspaces), Q-23 (CTWA attribution in v1),
Q-24 (existing leads E.164 already), Q-25 (res.partner field strategy)
— see `docs/planning/OPEN_QUESTIONS.md`. None block P2 *coding* but
Q-25 affects P7 enrichment design.

### Webhook URL to register on Hatif portal (when P2 ships)

For each channel in https://app.hatif.io/en/settings/api-connect set
**WhatsApp Webhook URL** to:

```
https://<your-public-odoo>/htf/webhook/whatsapp
```

And paste the per-channel `webhookSecret` Hatif provides into
**Settings → Hatif → Webhook Secret (current)** in Odoo.

For local dev, expose `http://localhost:8069` via cloudflared/ngrok:

```bash
# example
cloudflared tunnel --url http://localhost:8069
```

---

## 5. Standard workflow commands

```bash
# Edit code in ~/numo-hatif-odoo/htf_call_center/...

# Upgrade module on test db (uses real Hatif workspace)
docker exec odoo-app odoo -d test -u htf_call_center --stop-after-init --log-level=warn

# Restart container (needed when --dev=reload misses an inotify event)
docker compose -f /Users/amro/Downloads/Claude/ai-dnd-builder/odoo-local/docker-compose.yml restart odoo
sleep 5

# Drive Odoo shell for any verification
docker exec -i odoo-app odoo shell -d test --no-http --log-level=warn <<'PYEOF'
# your code here
PYEOF

# Run E2E suites (both must stay green)
python3 /tmp/htf_e2e_check.py    # P0 — 59/59
python3 /tmp/htf_p1_check.py     # P1 — 73/73

# Commit + push
cd ~/numo-hatif-odoo
git -c user.name='Amr Afifi' -c user.email='amr.sam.af@gmail.com' commit -am "feat(...): ..."
git push origin main
```

### JSON-RPC against test db

`test` db's admin user is Amr's email, not `admin/admin`. Either:

- Use `odoo shell` (no auth needed)
- Or ask Amr to run console snippets in his already-logged-in browser
- Or create a `hatf_uat_bot` user with known password if doing heavy
  automation (delete after — keeps workspace clean)

---

## 6. Sanity-check before declaring "session ready"

```bash
# Container up?
docker ps | grep odoo-app           # should show Up

# Module installed on test db?
docker exec odoo-db psql -U odoo -d test -c \
  "SELECT name, state FROM ir_module_module WHERE name='htf_call_center';"
# expect: htf_call_center | installed

# Settings tab actually renders?
# (next session needs Playwright MCP loaded — run: claude mcp list | grep playwright)

# Suites green?
python3 /tmp/htf_e2e_check.py | tail -3
python3 /tmp/htf_p1_check.py | tail -3
```

If everything above checks out → you're cleared to start P2.

Welcome back. Don't skip THE DRILL.
