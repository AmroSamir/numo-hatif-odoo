# numo-hatif-odoo

Odoo 19 Enterprise modules that integrate the **Hatif / Voxa BPaaS**
(telephony + WhatsApp Business API) into the Numo CRM.

## Modules

| Module | Status | Purpose |
|---|---|---|
| `htf_call_center` | **P0 shipped** — installable on Odoo 19 | Vendor wrapper: auth, HTTP client, HMAC webhook verification, signal bus, settings UI. No business endpoints yet. |
| `numo_crm_htf` | Planning only | Bridge: CRM-specific automation (AI summary card, sentiment trend, auto-stage progression, bulk WA send, daily digest). Empty until P7. **Not installable yet** — no `__manifest__.py`. |

Architecture, phase plan, data model, signal contract, and risk register live
under `htf_call_center/docs/planning/`. Start with `00_OVERVIEW.md`.

---

## First-time install — full command sequence

```bash
# 1. SSH to the server
ssh ubuntu@<server-ip>

# 2. Clone into the addons path (sudo required — root-owned dir)
cd /opt/odoo-erp-numo-sa/extra-addons
sudo git clone https://github.com/AmroSamir/numo-hatif-odoo.git

# 3. Hand ownership back to ubuntu so future `git pull` doesn't need sudo
sudo chown -R ubuntu:ubuntu numo-hatif-odoo

# 4. Symlink each module into the addons root so Odoo discovers them
#    (the clone puts modules one level deep under numo-hatif-odoo/)
cd /opt/odoo-erp-numo-sa/extra-addons
sudo ln -s numo-hatif-odoo/htf_call_center htf_call_center
sudo ln -s numo-hatif-odoo/numo_crm_htf    numo_crm_htf

# 5. Restart the Odoo container so it picks up the new module folders
cd /opt/odoo-erp-numo-sa
sudo docker compose restart web

# 6. Wait ~10s for Odoo to come back up, then in the browser:
#       Apps → Update Apps List
#       Apps → search "HTF Call Center" → Install
#       (numo_crm_htf is not installable yet — skip it)
```

> Prefer **symlinks** over `cp` so `git pull` updates both modules in one shot.
> If your container can't follow symlinks across mounts, replace step 4 with
> `sudo cp -r numo-hatif-odoo/htf_call_center .` and `cp` again on every update.

---

## Updating to the latest version

```bash
# 1. Pull
cd /opt/odoo-erp-numo-sa/extra-addons/numo-hatif-odoo
git pull origin main

# 2. Restart the Odoo container so new Python/XML/JS is picked up
cd /opt/odoo-erp-numo-sa
sudo docker compose restart web

# 3. In the browser:
#       Apps → Update Apps List
#       Apps → search "HTF Call Center" → Upgrade (not Install)
#
#    Then hard-refresh the browser tab to reload the OWL asset bundle:
#       Cmd+Shift+R   (macOS)
#       Ctrl+Shift+R  (Windows / Linux)
```

---

## Headless upgrade (no UI clicks)

Useful for CI / scripted deploys — runs the module upgrade inside the
container, then exits:

```bash
cd /opt/odoo-erp-numo-sa/extra-addons/numo-hatif-odoo
git pull origin main
cd /opt/odoo-erp-numo-sa
sudo docker compose exec web odoo \
    -u htf_call_center -d <db_name> --stop-after-init
sudo docker compose restart web
```

Once `numo_crm_htf` becomes installable (P7), add it to the `-u` list:
`-u htf_call_center,numo_crm_htf`.

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
