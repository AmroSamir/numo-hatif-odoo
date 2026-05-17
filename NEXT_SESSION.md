# Morning report — overnight unattended session, 2026-05-18

You said "finish a lot while I sleep" — here's what happened. **Read
this BEFORE doing anything else when you sit down**.

---

## TL;DR

- **P5 (IVR) removed** from the roadmap entirely per your call. Hatif
  portal owns IVR + bulk campaigns. P6→P5, P7→P6, etc. renumbered
  throughout `00_OVERVIEW.md` and `STATUS.md`.
- **P2 (WhatsApp Inbound) shipped** end-to-end. Webhook receiver, all
  10 message kinds, opt-out detector (English + Arabic with diacritic
  normalisation), STATUS transitions, signal bus, placeholder partner
  auto-create — every piece verified.
- **P3 backend (WhatsApp Outbound) shipped** — channel resolver, send
  service (with **live-send safety gate** OFF by default — see below),
  send wizard, retry cron, cost-by-category. UI (phone widget +
  chatter composer) **deferred** because they need browser verification.
- **Test scoreboard: 219/219 green** across all four phases
  (P0 59/59 + P1 73/73 + **P2 63/63** + **P3 backend 24/24**).
- **9 commits to `main`** during the session — listed at the bottom.
- **Three things need YOUR action** before live UAT — listed below.

---

## What you need to do this morning (in order)

### Step 1 — Generate `webhookSecret` for your two Hatif channels (~5 min)

Go to `https://app.hatif.io/en/settings/api-connect`. For each of the
two existing channels:

- `+966115001591` (أكاديمية نمو)
- `+966115001592` (الدعم الفني)

Set **WhatsApp Webhook URL** to (temporary local — see Step 2 for
tunnelling) and click "Generate Secret". Copy each secret.

### Step 2 — Decide tunnel strategy (~3 min decision, ~10 min setup)

We need to expose local `http://localhost:8069` to Hatif for live
UAT. Three options — tell me which when you're ready:

| Option | Pros | Cons |
|---|---|---|
| **cloudflared one-shot trial** | zero-config, free, instant | URL changes every run; you'd re-paste it into Hatif each time |
| **cloudflared named tunnel** | stable URL via your DNS (e.g. `htf-dev.numo.sa`), free | needs a `cloudflared` daemon as a system service + DNS record |
| **Go straight to prod** (`erp.numo.sa`) | no tunnel needed; uses real domain | requires deploying P2 to prod first; less freedom to iterate |

My recommendation: **named cloudflared tunnel** for active dev, then
flip to `erp.numo.sa` for staging/prod when P2 is signed off.

### Step 3 — Paste the secret into Odoo (~1 min)

```bash
docker exec -i odoo-app odoo shell -d test --no-http <<'PY'
env['htf.config'].set_param('webhook_secret_current', 'PASTE_HATIF_SECRET_HERE')
env.cr.commit()
print(env['htf.config'].webhook_secrets())
PY
```

(Run the same on the `odoo` db if you'll test against it instead.)

### Step 4 — Send a real test WA from your phone (~30 sec)

Send "hi" from your personal WhatsApp (`+966561868578`) to one of
the two Hatif channel numbers. Within seconds:

- a row should appear in **Settings → HTF → WhatsApp Messages** (admin
  debug view)
- a placeholder `res.partner` named "Hatif Contact …" gets created (or
  your existing partner gets the chatter post if your phone is already
  linked)
- partner chatter has the inbound bubble + the 24h window indicator
  turns green

If anything goes sideways, paste the failing webhook payload into
`htf_call_center/tools/fixtures/<name>.json` and run
`python3 htf_call_center/tools/replay_webhook.py --payload <path>` to
reproduce offline.

### Step 5 — Sign off P2 → I finish P3 UI

When Step 4 passes a green path, say **"P2 signed, finish P3"** and
I'll do the last two P3 pieces I deferred overnight (both need browser
verification):

- **T3.3 Phone widget** — replaces the standard Odoo phone widget on
  `res.partner` / `crm.lead` with `+966… [📞] [💬]`. The 💬 button
  opens the Send WhatsApp wizard (already shipped — see below).
- **T3.4 Chatter composer extension** — adds a WA toggle + channel
  picker to the standard chatter composer. WA toggle disables itself
  when the 24h window is closed (with tooltip).

### Step 6 — Test the outbound pipeline live (optional, low-risk)

The P3 backend is already shipped with a **safety gate**:
`htf.config.allow_real_outbound` defaults OFF — every send goes through
the full pipeline (DNC check + window check + channel resolution +
chatter post + signal fire) but **does NOT** call Hatif's API. Instead,
the message lands with a synthetic `dryrun:<uuid>` event id.

To flip the gate ON safely:

```bash
docker exec -i odoo-app odoo shell -d odoo --no-http <<'PY'
Cfg = env['htf.config']
# 1. (optional but recommended) whitelist your dev phone only
Cfg.set_param('outbound_phone_whitelist', '+966561868578')
# 2. flip the gate
Cfg.set_param('allow_real_outbound', 'True')
env.cr.commit()
print('Gate ON. Whitelist:', Cfg.get_param('outbound_phone_whitelist'))
PY
```

Then send a test from the wizard: open any partner with
`x_htf_last_inbound_at` set (your phone, after Step 4), click "Send
WhatsApp" → Type a message → Send. You'll get a real WA on your phone
if the whitelist matches.

To go back to dryrun mode:

```bash
docker exec -i odoo-app odoo shell -d odoo --no-http <<'PY'
env['htf.config'].set_param('allow_real_outbound', 'False')
env.cr.commit()
PY
```

---

## What got committed (9 commits, all pushed)

```
38fa271 docs(plan): skip P5 (IVR) entirely — Hatif portal owns IVR + campaigns
d535ff2 feat(htf.message): P2 T2.1 — WhatsApp message model + admin debug view
246fc2e feat(webhook): P2 T2.2 — POST /htf/webhook/whatsapp controller
29b1253 feat(htf-wa): P2 T2.3+T2.4+T2.5+T2.5b — full WhatsApp dispatcher pipeline
25b3d91 feat(htf-wa): P2 T2.6 + T2.7 — signal smoke + replay tool
e5f4ea5 test(htf-wa): P2 E2E suite — 63/63 green
8783776 docs(handoff): morning report after overnight P2 ship
9731c5b feat(htf-wa): P3 backend (T3.1b + T3.2 + T3.5 + T3.6 + T3.7)
<this commit> docs(handoff): refresh morning report after P3 backend ship
```

All pushed to `main` at https://github.com/AmroSamir/numo-hatif-odoo

---

## Files delivered

```
htf_call_center/
├── controllers/
│   ├── __init__.py
│   └── webhook_whatsapp.py          ← /htf/webhook/whatsapp (POST)
├── models/
│   └── htf_message.py               ← 33-field WA message record
├── services/
│   ├── whatsapp_inbound.py          ← inbound dispatcher (in/out STATUS)
│   ├── whatsapp.py                  ← outbound send_text + send_template
│   ├── channel_resolver.py          ← 5-step resolution chain
│   ├── chatter.py                   ← bubble renderers + status refresh
│   └── dnc_listener.py              ← opt-out keyword detector
├── wizards/
│   └── send_whatsapp.py             ← Send WhatsApp wizard
├── views/
│   ├── htf_message_views.xml        ← admin list + form
│   └── wizard_views.xml             ← +1 Send WhatsApp wizard view
├── data/
│   └── ir_cron.xml                  ← +1 retry cron
├── tools/
│   ├── signal_smoke.py              ← signal-bus smoke harness
│   ├── replay_webhook.py            ← CLI replay tool
│   ├── htf_p2_check.py              ← 63-assertion P2 E2E suite
│   ├── htf_p3_check.py              ← 24-assertion P3 backend E2E suite
│   └── fixtures/
│       ├── inbound_text.json
│       ├── inbound_image.json
│       ├── inbound_optout_arabic.json
│       └── outbound_status_read.json
└── security/ir.model.access.csv     ← +2 rows htf.message, +2 wizard
```

`__manifest__.py` updated with `views/htf_message_views.xml` in data.

---

## Notable design decisions made overnight

### Composite idempotency key

Hatif reuses the SAME `messageId` across the outbound lifecycle
(Sent → Delivered → Read → Failed), so the original "use `messageId`
as the dedupe key" plan would have collapsed every status transition
to a single 200-OK no-op. The controller now uses
`<messageId>:<status>:<direction>` as the idempotency key. This keeps
each transition addressable while still collapsing genuine Hatif
retries (same status, same direction).

This was caught during the first E2E pass and fixed before the commit
that introduced T2.3 — would have been a nasty production bug.

### Placeholder partners on unknown contactId

The WhatsApp webhook payload does NOT include the contact's phone
number — only Hatif's `contactId` UUID. To avoid blocking the webhook
on a synchronous `/v1/contacts/{id}` fetch, we create a placeholder
`res.partner` named `Hatif Contact <short-uuid>` and an
`htf.contact.link` row with `sync_state='pending'`. The contacts-poll
cron (already shipped in P1) will backfill name + phone on its next
run.

### Opt-out detector: Arabic-aware whole-message matching

The DNC detector strips diacritics (NFKD + combining-mark removal)
and normalises alefs (إ/أ/آ → ا) so `إلغاء الاشتراك` matches
`الغاء الاشتراك`. Matching is **strict whole-message** —
"Stop, my order is wrong" does NOT trigger STOP. We'd rather miss a
real opt-out than annoy a paying customer who didn't intend it. The
keyword list is configurable via `htf.config.dnc_keywords`.

### Outbound from Hatif portal still gets logged

If a Numo agent sends WA directly from the Hatif portal (not via
Odoo P3), the resulting outbound STATUS webhook hits our same
endpoint. The dispatcher detects "outbound with no pre-existing
htf.message row" and creates one + posts to chatter. So even before
P3 ships, every WA conversation Numo agents have shows up in Odoo
chatter automatically.

### Recording auto-bubble refresh

Status updates (Sent → Delivered → Read → Failed) edit the existing
`mail.message.body` in place instead of posting a new chatter row.
That means each outbound message produces ONE chatter bubble that
visually progresses through ✓ → ✓✓ → read → ⚠️ states, not four
separate bubbles. Stored as `htf.message.chatter_message_id`.

---

## What's NOT done (deferred — need browser verification or future phases)

**Deferred from P3 because they're OWL UI work:**

- **Phone widget on `res.partner` / `crm.lead`** with deep-link to
  Hatif app + WA composer → P3 T3.3. The wizard the widget would
  open (Send WhatsApp) IS shipped — just no widget button yet.
- **Chatter composer extension** for outbound WA → P3 T3.4. Right now
  agents click "Send WhatsApp" from the partner form Action menu.

**Deferred to later phases by design:**

- **`htf.dnc` model + bridge subscriber on `htf.wa.optout`** → P6
  (CRM Enrichment). For now the inbound message gets
  `is_opt_out=True` and the signal fires; the bridge does the
  partner-level DNC flip later. The Send WA service already respects
  `partner.x_htf_opted_out` so DNC works end-to-end via the partner
  flag.
- **media URL → ir.attachment caching** → P4 calls phase (Q-15
  ANSWERED-PARTIAL). For v1 we link the URL directly in chatter;
  you'll see a broken link if it expires.
- **Live tunnel + Hatif portal config** → blocked on Steps 1-3 above.

---

## How to run the suites yourself

```bash
# All four should be green
python3 /tmp/htf_e2e_check.py        # P0           → 59/59
python3 /tmp/htf_p1_check.py         # P1           → 73/73
python3 /tmp/htf_p2_check.py         # P2 inbound   → 63/63
python3 /tmp/htf_p3_check.py         # P3 backend   → 24/24
# Combined: 219/219.
```

P2 suite hits live HTTP (`localhost:8069`); P3 suite drives the
ORM via odoo shell (faster, no HTTP). The container must be up.

P2 suite auto-sets `webhook_secret_current=p2-test-secret` on the
`odoo` db if not already set — that's the suite's secret, separate
from whatever you'll get from Hatif in Step 1.

P3 suite expects an `htf.channel` row + a workspace fallback in
`htf.config.default_outbound_wa_channel_id`. It creates one and
commits before the test run. Both safe to re-run.

---

## Resume point after P3 UI

When you say "P2 signed, finish P3" I'll do the OWL UI:

1. **T3.3 phone widget** — `static/src/components/HatifPhoneField/`
   replacing the standard Odoo phone widget on `res.partner` /
   `crm.lead` with `+966… [📞] [💬]`. The 📞 button opens `tel:` deep
   link, 💬 opens the Send WhatsApp wizard.
2. **T3.4 chatter composer extension** — WA toggle + channel picker on
   standard mail composer. Disabled when 24h window is closed.
3. Update `htf_p3_check.py` to drive the widget via Playwright (or
   describe a manual UAT checklist if Playwright isn't set up).

After P3 fully ships, **P4 (Calls)** is next: Hatif Call Webhook,
recording link in chatter, ingest transcription/Summary/sentiment from
Hatif into `htf.call`, fire `htf.call.received` / `htf.call.missed`
signals. Read `htf_call_center/docs/planning/P4_CALLS.md`.

---

Welcome back. Don't skip THE DRILL.

— overnight Claude
