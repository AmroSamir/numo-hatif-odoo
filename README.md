# numo-hatif-odoo

Odoo 19 Enterprise modules that integrate the **Hatif / Voxa BPaaS**
(telephony + WhatsApp Business API) into the Numo CRM.

## Modules

| Module | Status | Purpose |
|---|---|---|
| `htf_call_center` | **P0 shipped** — installable on Odoo 19 | Vendor wrapper: auth, HTTP client, HMAC webhook verification, signal bus, settings UI. No business endpoints yet. |
| `numo_crm_htf` | Planning only | Bridge: CRM-specific automation (AI summary card, sentiment trend, auto-stage progression, bulk WA send, daily digest). Empty until P7. |

Architecture, phase plan, data model, signal contract, and risk register live
under `htf_call_center/docs/planning/`. Start with `00_OVERVIEW.md`.

## Deploy on staging

The Odoo container's addons path expects each module at the root of
`/mnt/extra-addons/` (or wherever your container mounts addons). Pull the repo
to a working directory, then copy the two module folders into place:

```bash
# on the server
cd /tmp
git clone https://github.com/AmroSamir/numo-hatif-odoo.git
sudo cp -r numo-hatif-odoo/htf_call_center /opt/odoo19e-docker/extra-addons/
sudo cp -r numo-hatif-odoo/numo_crm_htf    /opt/odoo19e-docker/extra-addons/
sudo chown -R 101:101 /opt/odoo19e-docker/extra-addons/htf_call_center \
                       /opt/odoo19e-docker/extra-addons/numo_crm_htf
# restart the staging container
docker compose restart web_odoo_staging
```

Then in Odoo: **Apps → Update Apps List → Install "HTF Call Center"**.

> `numo_crm_htf` is not installable yet — no `__manifest__.py`. Skip it
> until P7 lands.

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

## Public API contract (for the bridge)

The bridge (`numo_crm_htf`) and any future consumer MUST go through:

```python
service = env['htf.config'].get_service('auth' | 'http' | ...)
```

Directly importing `htf_call_center.services.*` or `htf_call_center.models.*`
is blocked by the pylint plugin at `htf_call_center/tools/pylint_htf_no_internal_import.py`.

Public surface modules are:

- `htf_call_center.constants`
- `htf_call_center.exceptions`
- `htf_call_center.signals` (the `htf_signals` singleton)

## Linting the boundary

```bash
# from the repo root
python htf_call_center/tools/pylint_htf_no_internal_import.py numo_crm_htf/
# exit 0 = clean; exit 1 = bridge crossed the boundary
```

## License

LGPL-3 — matches the Odoo modules convention.
