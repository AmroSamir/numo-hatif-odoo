# Deployment

How code reaches staging then production. No surprises.

---

## Environments

| Env | Container | URL | DB |
|---|---|---|---|
| Local dev | docker-compose | http://localhost:8069 | dev |
| Staging | `web_odoo_staging` | https://staging.numo.sa (or current staging hostname) | numo_staging |
| Production | `web_odoo` | https://erp.numo.sa | numo |

(Hostname `erp.numo.sa` confirmed during planning; production hostname migration plan owned outside this doc.)

---

## Pre-flight (one time)

1. Hatif team provisions a workspace + webhook secret(s)
2. Webhook URLs registered with Hatif team:
   - `https://staging.numo.sa/htf/webhook/call`
   - `https://staging.numo.sa/htf/webhook/whatsapp`
   - `https://staging.numo.sa/htf/webhook/ivr`
   - (and prod equivalents)
3. Hatif IP allowlist provided to ops (if applicable)
4. Test connection from Odoo Settings page succeeds against Hatif sandbox

---

## Module install order (always)

1. Backup DB + filestore
2. Pull latest from git on server: `cd /opt/odoo19e-docker && git pull origin main`
3. Install/upgrade `htf_call_center` first
4. Install/upgrade `numo_crm_htf` second
5. Verify install: `Settings → Apps`, both green
6. Run `Test Connection` button on `Settings → Hatif`
7. Replay a known-good webhook payload via curl with valid HMAC → verify chatter post appears

If step 6 or 7 fails → roll back (see Rollback below).

---

## Standard deploy (staging)

```bash
ssh root@SERVER 'bash /opt/odoo19e-docker/scripts/deploy-staging.sh'
```

Script does:
- git pull
- docker compose restart web_odoo_staging
- pre-warm: `odoo -d numo_staging -u htf_call_center,numo_crm_htf --stop-after-init`

Success criteria:
- Containers up
- Both modules show `installed` / `upgraded`
- No error logs in last 5 min

---

## Promotion to production

After staging UAT signed off:

```bash
ssh root@SERVER 'bash /opt/odoo19e-docker/scripts/deploy-prod.sh'
```

**Approval gate:** Amr explicitly approves each prod promotion in writing (per memory rule: NEVER touch prod without approval).

---

## Rollback

If anything breaks:

1. Stop Odoo container
2. Restore DB from backup taken before deploy
3. Restore filestore from backup
4. `git checkout <previous-commit>` in `/opt/odoo19e-docker`
5. Restart container
6. Notify users

Rollback target time: < 15 minutes.

---

## Webhook URL rotation

When rotating HMAC secrets:

1. Save NEW secret as `webhook_secret_current`
2. Move OLD secret to `webhook_secret_previous`
3. Hatif side switches to NEW secret
4. After 7 days (overlap window), clear `webhook_secret_previous`

The wrapper accepts BOTH secrets during overlap.

---

## Database migrations

Each phase's models include a migration script in `htf_call_center/migrations/19.0.X.Y.Z/pre-migration.py` and/or `post-migration.py` if needed.

For schema additions only (most cases): no migration script needed, Odoo's standard upgrade handles it.

For renames or data transforms: explicit script with rollback section.

---

## Feature flags

The bridge supports feature flags via `ir.config_parameter`:

- `numo_crm_htf.enable_auto_stage` (default True)
- `numo_crm_htf.enable_won_lost_hooks` (default True)
- `numo_crm_htf.enable_daily_digest` (default True)
- `numo_crm_htf.enable_ai_extraction` (default False — opt-in v1)

Flip in Settings → Technical → Parameters without redeploying.

---

## Monitoring

- Odoo built-in `ir.logging` for error tracking
- Failed webhook signature attempts → log line `[htf] HMAC fail src=<ip>`
- Sumo of failed sends per day → daily admin email
- Cron job heartbeat: `numo_crm_htf.daily_digest` writes a heartbeat row each run, alert if missing for > 25h
- Uptime: rely on existing erp.numo.sa monitoring; webhook routes piggyback

---

## Secrets distribution

- Production secrets stored in `htf.config` only — accessible via Settings → Hatif → Connection
- Staging secrets distinct from production
- Local dev: use a Hatif sandbox token (Hatif team provides)
- NEVER commit secrets to git; .env files git-ignored

---

## Backup retention

Standard Numo Odoo backup policy (already in place) covers DB + filestore. Hatif call recordings remain on Hatif side; we do not back them up unless we explicitly cache them.

---

## Version compatibility

| `htf_call_center` | `numo_crm_htf` | Compatible |
|---|---|---|
| 19.0.1.x.y | 19.0.1.x.y | ✓ |
| 19.0.2.x.y | 19.0.2.x.y | ✓ |
| 19.0.1.x.y | 19.0.2.x.y | bridge MUST tolerate older wrapper one minor version |

Cross-major upgrades require simultaneous deploy.
