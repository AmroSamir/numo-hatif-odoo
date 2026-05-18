# NEXT SESSION — start here

Last updated: **2026-05-19** — after P2 + P3 went live on `erp.amro.pro`.

---

## TL;DR

**You're picking up after a major milestone.** P0–P3 are live on the
test ERP at `https://erp.amro.pro`. A real WhatsApp message round-trip
was confirmed in both directions against the real Numo Hatif workspace.

| Phase | Status |
|---|---|
| P0 Foundation | ✅ live |
| P1 Channels + Contacts + Users | ✅ live (2 channels, 7 users, 1 tag) |
| P2 WhatsApp Inbound | ✅ **LIVE-UAT'd** — real phone → Odoo chatter |
| P3 WhatsApp Outbound | ✅ **LIVE-UAT'd** — Odoo wizard → real phone |
| P4 Calls Webhook | ▶️ **NEXT** |

E2E suites scoreboard locally:
- P0 → 59/59
- P1 → 73/73
- P2 → 63/63
- P3 backend → 24/24
- P3 UI → 17/17
- **Total local: 236/236**

GitHub: https://github.com/AmroSamir/numo-hatif-odoo (branch `main`)
Last commit landed on staging: `664a5e4` (or later — `git pull` first)

---

## Where things live

### Code
- Local working dir: `~/numo-hatif-odoo/`
- GitHub: `https://github.com/AmroSamir/numo-hatif-odoo` (source of truth)
- Bind-mount on local OrbStack: `~/numo-hatif-odoo/{htf_call_center,numo_crm_htf} → /mnt/extra-addons/`
- Bind-mount on staging server: `/opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/` (with two symlinks `htf_call_center` and `numo_crm_htf` pointing into it)

### Environments

| Env | URL | DB | Container | Notes |
|---|---|---|---|---|
| Local — empty | `http://localhost:8069` → DB `odoo` | `odoo` | `odoo-app` (OrbStack) | Starter DB, only mail+contacts+htf installed |
| Local — full | DB `test` (same container) | `test` | `odoo-app` | Full module suite, used for live UAT against real Hatif workspace |
| Staging | `https://erp.amro.pro` | `numo` | `web-erp-amro-pro` | **Where P2 + P3 are live-verified** |
| Numo prod | `https://erp.numo.sa` | `numo` | TBD | Same DB name. Deploy pattern mirrors staging. |

### Planning docs
- `htf_call_center/docs/planning/00_OVERVIEW.md` — phase index
- `htf_call_center/docs/planning/STATUS.md` — phase tracker + changelog
- `htf_call_center/docs/planning/OPEN_QUESTIONS.md` — Q-XX tracking
- `htf_call_center/docs/planning/RISK_REGISTER.md` — risk table
- `htf_call_center/docs/planning/P4_CALLS.md` — read this before P4 work
- `htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md` — draft email to Hatif support (newly added)

### E2E suites (run locally — all must stay green)
```bash
python3 /tmp/htf_e2e_check.py     # P0 → 59/59
python3 /tmp/htf_p1_check.py      # P1 → 73/73
python3 /tmp/htf_p2_check.py      # P2 inbound → 63/63
python3 /tmp/htf_p3_check.py      # P3 backend → 24/24
python3 /tmp/htf_p3_ui_check.py   # P3 UI → 17/17
```

---

## Read THE DRILL before touching code

`~/Downloads/Claude/odoo-modules/CLAUDE.md` opens with **THE DRILL**.
It's non-negotiable:

1. Edit code → re-read file to confirm change actually landed
2. Upgrade module via `docker exec odoo-app odoo -d test -u htf_call_center --stop-after-init --log-level=warn`
3. Restart container — `--dev=reload` on OrbStack misses inotify events
4. Exercise the actual feature path end-to-end
5. Verify the user-visible goal is met
6. Only then ask Amr to verify in browser; report includes proof
7. Push to GitHub once Amr signs off

The DRILL also has 17 Odoo-19 footguns logged. Re-read them before
touching XML, security, fields, or wizards.

---

## What's NEXT — P4 Calls Webhook

Same architectural pattern as P2 (WhatsApp Inbound). Hatif sends call
events to a Post-call Webhook URL when calls complete; we ingest them
into Odoo as `htf.call` records, post to chatter, fire signals.

### Tasks (read `P4_CALLS.md` for the spec)

| Task | Effort | Output |
|---|---|---|
| T4.1 `htf.call` model | 1h | All fields from Hatif's Call Webhook payload (status int, type int, callerNumber, calleeNumber, pickupTime, hangupTime, recordingUrl, **transcription.text** + **transcription.words[]**, **Summary**, sentiment) |
| T4.2 Webhook controller | 1.5h | `POST /htf/webhook/call`, same HMAC + idempotency + dev_mode_skip_hmac escape as P2 |
| T4.3 Call dispatcher service | 2h | Branch by `status` (0=Active / 1=Completed / 2=Missed / 3=RejectedByCaller / 4=RejectedByCallee / 5=NoAnswer / 6=Cancelled / 7=Failed); partner resolution; htf.call persist; signal fire |
| T4.4 Audio player widget | 1.5h | Inline `<audio>` element on htf.call form pointing at recordingUrl (stream from Hatif per Q-15) |
| T4.5 Transcription widget | 2h | Render `transcription.words[]` as a clickable transcript that scrubs to the audio timestamp on click; speaker labels if Hatif provides them |
| T4.6 Chatter post for calls | 1.5h | Inbound/outbound bubble on partner chatter with duration, status icon, recording link, Summary preview |
| T4.7 Phone widget call-button wired | 0.5h | Hook the 📞 button on htf_phone widget into a "tel:" deep-link (already works); upgrade to Hatif app scheme if Hatif documents one |
| T4.8 Lead form smart buttons | 1h | "X calls" smart button on crm.lead form via x_htf_call_count |
| T4.9 Missed call activity creator | 1h | When status=Missed → create `mail.activity` on partner with type `to_do` and summary "Call back" |
| T4.10 P4 E2E suite | 1h | `/tmp/htf_p4_check.py` — target 40+ assertions across all status types + transcript ingest |

**Total estimate:** ~12-14h work. Same as my P2 spend.

### Deploy after coding
Same pattern as the P2 + P3 deploy that just landed on `erp.amro.pro`:

```bash
# On staging server
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo/
git pull origin main

docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml stop web
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml run --rm web \
    odoo -d numo -u htf_call_center --stop-after-init --no-http --log-level=warn 2>&1 | tail -10
docker compose -f /opt/odoo-erp-amro-pro/docker-compose.yml up -d web
sleep 6
```

Then on Hatif portal: each channel's **Post-call Webhook URL** →
paste `https://erp.amro.pro/htf/webhook/call`. Place a test call to
`+966 11 500 1591` and confirm the htf.call row + chatter post appears.

---

## Things to do BEFORE P4 (defence-in-depth follow-up)

These came out of the P2/P3 live UAT. None are blocking P4, but
they should land soon:

### 1. Email Hatif support about webhook signing
Draft is ready at:
`htf_call_center/docs/HATIF_SUPPORT_WEBHOOK_SIGNING_REQUEST.md`

Send it via Hatif support / their account manager. Until they confirm
signing + give us the per-channel `webhookSecret`, our
`dev_mode_skip_hmac=True` setting is what makes inbound work.

### 2. Add Nginx IP allowlist for Hatif source IPs
We've only seen `8.213.48.16` so far. Add a location-specific allow
rule in Nginx so that even though HMAC is bypassed, only Hatif's IPs
can reach `/htf/webhook/whatsapp` (and later `/htf/webhook/call`):

```nginx
location /htf/webhook/ {
    allow 8.213.48.16;
    # add more if Hatif publishes a range
    deny all;
    proxy_pass http://odoo;
}
```

(Confirm Hatif's full source IP range in the support email above.)

### 3. Disable `dev_mode_skip_hmac` once signing is back
When Hatif confirms signing + secrets:
```bash
docker exec db-erp-amro-pro psql -U odoo -d numo -c \
  "UPDATE ir_config_parameter SET value='False' WHERE key='htf_call_center.dev_mode_skip_hmac';"
# + restart web container to bust ormcache
```

---

## Notable design decisions made during P2+P3 live UAT

### Hatif does not sign webhooks (Q-03 contradicted by reality)
Their apidog spec claims HMAC-SHA256 in `X-Voxa-Signature`. Live
delivery shows NO signature header at all. We're working around it
with `dev_mode_skip_hmac`. Track resolution via the support email.

### Composite idempotency key for outbound STATUS lifecycle
Hatif reuses the SAME `messageId` across Sent → Delivered → Read →
Failed transitions, so a bare `messageId` dedupe key falsely collapsed
all transitions into one event. Controller now uses
`<messageId>:<status>:<direction>` — each transition is addressable
but genuine retries (same status/direction) still collapse.

### Channel resolver 5-step chain
For outbound: `lead.team → partner.team → partner override →
sender_user.team → htf.config workspace fallback`. Anything that
doesn't resolve raises `HtfChannelNotFoundError` with admin-readable
hints.

### Phone canonicalization for whitelist
`outbound_phone_whitelist` is compared after both sides go through
`utils.phone.normalize_e164` (the KSA-aware phonenumbers wrapper).
Handles `0561868578`, `966561868578`, `+966 56 186 8578`,
`966056xxxxx`, etc. all collapsing to `+966XXXXXXXXX`.

### CRM dependency added
`htf_call_center` was intentionally CRM-agnostic at start. Live UAT
proved the real user surface is `crm.lead` forms (sales agents live
there). Added `crm` to depends so the htf_phone widget + Send WA
header button apply on lead forms too. Bridge module `numo_crm_htf`
still planned for richer CRM workflows in P6.

### Channels list create='0' + ⚙ Actions menu wizards
Admins must not manually create channels (they come from Hatif sync).
The Channels list has `create='0'` and surfaces "Sync Channels from
Hatif" + "Bind Channels to Teams" via the ⚙ Actions dropdown.
Empty-state CTA explains the workflow.

### PII placeholder convention
Use `+966XXXXXXXXX` for the dev phone in all code/docs. Amr's real
number was scrubbed on 2026-05-19; git history still contains it.

---

## Sanity-check checklist when you sit down

```bash
# Local container up?
docker ps | grep odoo-app

# Module installed locally?
docker exec odoo-db psql -U odoo -d test -c \
  "SELECT name, state FROM ir_module_module WHERE name='htf_call_center';"

# All 5 suites green?
python3 /tmp/htf_e2e_check.py | tail -3
python3 /tmp/htf_p1_check.py | tail -3
python3 /tmp/htf_p2_check.py | tail -3
python3 /tmp/htf_p3_check.py | tail -3
python3 /tmp/htf_p3_ui_check.py | tail -3

# Staging healthy?
curl -I https://erp.amro.pro/web/login 2>&1 | head -3
```

---

## Open Questions still pending answers (only for P6+/P7+ work)

| Q | Owner | Status | Topic |
|---|---|---|---|
| Q-02 | Hatif | ASSUMED | IP allowlist |
| Q-03 | Hatif | **ACTIVELY CONTRADICTED** | HMAC signing — see support email draft |
| Q-06 | Hatif | ASSUMED | Recording URL expiry |
| Q-19 | answered | | Hatif provides transcription + Summary + sentiment — use them in P9 |
| Q-26/27 | Hatif | ASSUMED | Metrics endpoints |
| Q-28 | Hatif | DEFERRED | AI agent API |

All Amr-owned Qs are resolved. The 3 still open (Q-14, Q-16, Q-30)
were answered before P3 shipped.

---

Welcome back. Don't skip THE DRILL. P4 next.

— end of NEXT_SESSION.md
