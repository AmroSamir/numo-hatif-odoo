# numo-hatif-odoo

Odoo 19 Enterprise modules that integrate the **Hatif / Voxa BPaaS**
(telephony + WhatsApp Business API) into the Numo CRM.

## Modules

| Module | Status | Purpose |
|---|---|---|
| `htf_call_center` | **v19.0.1.27.0** — installable on Odoo 19 | Hatif integration: auth + HTTP client + HMAC webhook verification, raw data models, calls + WhatsApp + IVR + Discuss mirror, P0–P8 features shipped. |
| `numo_crm_htf` | Planning only | Bridge: CRM-specific automation (AI summary card, sentiment trend, auto-stage progression, bulk WA send, daily digest). **Not installable yet** — no `__manifest__.py`. |

Architecture, phase plan, data model, signal contract, and risk register live
under `htf_call_center/docs/planning/`. Start with `00_OVERVIEW.md`.

---

## Installation guide

### Prerequisites

- **Odoo 19 Enterprise** (Community will not work — the OWL Discuss patches
  assume the enterprise bundle, and several Odoo 19 API renames are hard
  pre-reqs: `res.groups.user_ids`, `res.users.group_ids`,
  `ir.cron` without `numbercall`, `models.Constraint` instead of `_sql_constraints`).
- Python 3.12+ with `requests` and `phonenumbers` packages.
- Postgres 14+ (the test rig uses 15; nothing version-specific in the schema).
- Filesystem write access to the Odoo addons path (for `git clone`).

### Quick install — Ubuntu + Docker Compose (Numo's reference layout)

If your server matches the Numo reference layout (Ubuntu VM, Docker
Compose at `/opt/odoo-erp-numo-sa/`, extra-addons at
`/opt/odoo-erp-numo-sa/extra-addons/`, `web` container), paste this
sequence end-to-end:

```bash
# 1. Clone into the extra-addons folder
cd /opt/odoo-erp-numo-sa/extra-addons
sudo git clone https://github.com/AmroSamir/numo-hatif-odoo.git
sudo chown -R ubuntu:ubuntu numo-hatif-odoo     # so future `git pull` is sudo-free

# 2. Symlink the installable module one level up (Odoo only scans direct children)
sudo ln -s numo-hatif-odoo/htf_call_center htf_call_center
ls -la htf_call_center/__manifest__.py          # sanity check — should print the manifest path

# 3. Install Python deps inside the running Odoo container
cd /opt/odoo-erp-numo-sa
docker compose ps                                # confirm the container name (assumed `web` below)
docker compose exec web pip install --break-system-packages requests phonenumbers

# 4. Restart the container so it picks up the new module folder
docker compose restart web && sleep 8

# 5. In the browser:
#       Apps → top-right ⋮ → Update Apps List → Update
#       Apps → search "HTF Call Center" → Install
```

That's it for installation. Skip ahead to **Step 5 — configure
credentials** below when you're ready to wire up Hatif.

If your server is NOT the Numo layout (different paths, different
container name, system Odoo instead of Docker, etc.), follow the
detailed walkthrough below instead.

---

### Detailed walkthrough (any layout)

#### Step 1 — find your addons path

You need one directory that's already in Odoo's `addons_path`. The exact
location depends on how you installed Odoo:

| Install style | Typical host path |
|---|---|
| **Docker (compose)** | bind-mounted from host into `/mnt/extra-addons` — check `docker-compose.yml`'s `volumes:` |
| **System (apt / native)** | `/opt/odoo/custom-addons` or `/var/lib/odoo/addons/19.0` |
| **Odoo.sh** | the repo root of your project (the platform syncs your GitHub repo automatically) |

Confirm with:
```bash
# Docker
docker exec <odoo-container> odoo --addons-path-show 2>&1 | head -3

# System
sudo -u odoo odoo --addons-path-show 2>&1 | head -3
```

#### Step 2 — clone the repo into your addons path

```bash
# Replace /YOUR/ADDONS/PATH with whatever you confirmed in Step 1.
cd /YOUR/ADDONS/PATH
git clone https://github.com/AmroSamir/numo-hatif-odoo.git
```

Odoo discovers modules as **direct children** of addons-path entries, but
the repo nests modules one level deep. Two ways to fix that:

**Option A — symlinks (recommended, one-shot updates):**
```bash
cd /YOUR/ADDONS/PATH
ln -s numo-hatif-odoo/htf_call_center htf_call_center
# numo_crm_htf is not installable yet — skip until it has a manifest.
```

**Option B — extend `addons_path`** in `odoo.conf` so the nested folder
is also scanned:
```ini
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/YOUR/ADDONS/PATH,/YOUR/ADDONS/PATH/numo-hatif-odoo
```
Restart Odoo after editing.

#### Step 3 — install Python dependencies

The module imports `requests` and `phonenumbers`. Without these the
install hard-crashes at module import time.

**Docker:**
```bash
docker exec <odoo-container> pip install --break-system-packages requests phonenumbers
# To persist across container recreation: add the two packages to your
# Dockerfile or compose's `pip_install` extension, then rebuild.
```

**System:**
```bash
sudo pip3 install requests phonenumbers
sudo systemctl restart odoo
```

#### Step 4 — install via the Odoo UI

1. Log in as Administrator.
2. **Apps** → top-right ⋮ menu → **Update Apps List** → Update.
3. Search **"HTF Call Center"**.
4. Click **Install**.

The install:
- Creates the `Hatif: User` and `Hatif: Administrator` groups.
- Adds `base.user_root` and `base.user_admin` to `Hatif: Administrator`.
- Seeds the Hatif logo as the avatar for `base.public_partner` (used as
  the inbound-webhook author placeholder until Step 5 maps real agents).
- Schedules two crons: token refresh (every 30 min) and webhook-event
  purge (daily).

#### Step 5 — configure credentials (do this before any feature works)

**Settings → Hatif** (Administrator only):

| Field | Where to find it |
|---|---|
| `client_id` | Hatif workspace settings → API → Service Account |
| `client_secret` | Same screen, click "Reveal" (only shown once at creation) |
| `webhook_secret_current` | Hatif workspace settings → Webhooks → Signing key |
| Default country code | Your tenant's primary E.164 country (e.g. `966` for KSA) |

Then click **Test Connection** — expect a green "Token acquired" toast.
If you see an auth error, double-check the secret has no trailing whitespace.

#### Step 6 (only if you want WhatsApp sending) — Map Users wizard

1. Open the Hatif app → **Map Users Wizard** → click "Sync from Hatif".
2. For each Hatif workspace user that's also an Odoo user, pick the
   matching Odoo user from the **Odoo User** dropdown.
3. In **Allowed Hatif Channels**, pick the channel(s) each agent works.
   (Channel selection is the access gate — agents not mapped here cannot
   open the Send WhatsApp wizard.)
4. **Save**.

The save automatically grants `Hatif: User` to every mapped agent and
adds them to the corresponding Hatif Discuss channels for their assigned
CRM leads. Re-save anytime you change assignments.

---

## Updating to a newer version

### Numo reference layout (one-liner)

```bash
cd /opt/odoo-erp-numo-sa/extra-addons/numo-hatif-odoo && git pull origin main \
  && cd /opt/odoo-erp-numo-sa && docker compose restart web
```

Then in the browser: **Apps → search "HTF Call Center" → Upgrade**.

### Generic (any layout)

```bash
cd /YOUR/ADDONS/PATH/numo-hatif-odoo
git pull origin main

# Restart Odoo so all workers pick up new Python / XML / JS:
docker compose restart web         # Docker
sudo systemctl restart odoo        # System
```

Then in the browser: **Apps → search "HTF Call Center" → Upgrade**
(not Install). After upgrade, hard-refresh the tab to drop the cached
OWL asset bundle:
- macOS: `Cmd+Shift+R`
- Windows / Linux: `Ctrl+Shift+R`

Migrations under `htf_call_center/migrations/<version>/` fire
automatically on every version bump — no manual SQL needed.

### Headless upgrade (CI / scripted deploys)

```bash
cd /YOUR/ADDONS/PATH/numo-hatif-odoo && git pull origin main

# Stop workers, run one-shot upgrade, restart workers.
docker compose stop web
docker compose run --rm web odoo -d <db_name> -u htf_call_center --stop-after-init
docker compose up -d web
```

This is what `htf_call_center/tools/deploy.sh` does. On servers that
already have a checkout, just `bash htf_call_center/tools/deploy.sh`
after a `git pull` and you're done.

---

## Uninstall

1. **Apps → HTF Call Center → Uninstall** (UI confirms it'll drop the
   tables it owns).
2. Optional cleanup if you also want to remove the host files:
   ```bash
   cd /YOUR/ADDONS/PATH
   rm htf_call_center                              # the symlink, if used
   rm -rf numo-hatif-odoo                          # the clone
   ```

Uninstall is safe — every `discuss.channel.x_htf_*` field is nullable
with a `set null` ondelete, so standard Discuss channels keep working
even with the module gone.

---

## P0 acceptance checklist (`htf_call_center`)

1. Module installs cleanly on a fresh DB
2. **Settings → Hatif** page renders all sections (Connection / Webhook
   signing / Polling / Defaults / Debug)
3. Enter `client_id` + `client_secret` (and optionally `webhook_secret_current`)
4. Click **Test Connection** → expect "Token acquired" toast
5. Toggle **Debug Logging** → re-test → confirm bodies log but bearer tokens
   are stripped (filter in `log_redaction.py`)
6. Inspect the auto-created crons under **Settings → Technical → Scheduled
   Actions**: `HTF: refresh OAuth token` (30 min), `HTF: purge old webhook
   events` (daily)
7. Uninstall the module → DB clean, no residue

---

## Public API contract (for the bridge)

The bridge (`numo_crm_htf`) and any future consumer MUST go through:

```python
service = env['htf.config'].get_service('auth' | 'http' | ...)
```

Directly importing `htf_call_center.services.*` or `htf_call_center.models.*`
is blocked by the pylint plugin at
`htf_call_center/tools/pylint_htf_no_internal_import.py`.

Public surface modules are:

- `htf_call_center.constants`
- `htf_call_center.exceptions`
- `htf_call_center.signals` (the `htf_signals` singleton)

### Linting the boundary

```bash
# from the repo root
python htf_call_center/tools/pylint_htf_no_internal_import.py numo_crm_htf/
# exit 0 = clean; exit 1 = bridge crossed the boundary
```

---

## License

LGPL-3 — matches the Odoo modules convention.
