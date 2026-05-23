# NEXT SESSION — start here

Last updated: **2026-05-23** (end of session)

Short follow-up session on top of yesterday's v19.0.1.26.0 push. The
InPrivate browser test surfaced a P8 regression — assigned salespeople
hit AccessError on the Send WhatsApp wizard because P8 only managed
channel membership, not the `Hatif: User` group ACL. Redesigned the
whole access model around a 2-gate intersection (channel mapping + lead
salesperson) and shipped v19.0.1.27.0 to GitHub. **NOT yet deployed to
prod — user chose push-only.** Also rewrote the install README so the
module works on a fresh Ubuntu+Docker server (Numo's new `web-vm` at
`/opt/odoo-erp-numo-sa/extra-addons`).

GitHub: https://github.com/AmroSamir/numo-hatif-odoo
Latest commit on `main`: `cc9f3aa docs(readme): add Numo Ubuntu+Docker quick-install block and one-line update`
Module version on GitHub: `19.0.1.27.0`
Module version on prod (`erp.amro.pro`): still `19.0.1.26.0` — **needs deploy**
Test scoreboard: **303/309** local (e2e 59, p1 72, p2 62, p3 24, p3_ui 17, p4 37, p7 32 — same 6 pre-existing failures as session-close yesterday; 9 NEW assertions in p7 [8] for the 2-gate model all pass).

---

## 30-second TL;DR

P8's channel-membership privacy fix worked, but locked out the
assigned salespeople too because they aren't in the `Hatif: User`
group. v19.0.1.27.0 rebuilds access as: **CHANNEL gate (Map Users
wizard) AND LEAD gate (crm.lead.user_id)** — both must pass. Auto
grants/revokes `Hatif: User` when channel mappings change. Code is on
GitHub; prod deploy is the next physical step.

---

## What shipped today (1 feature commit + 2 docs, v19.0.1.26.0 → v19.0.1.27.0)

### Feature — 2-gate Hatif channel access (commit `2595293`)

**The bug:** an assigned CRM salesperson (in screenshot, lead 5810 "my
personal number" → Salesperson "Amr Afifi" → channel "أكاديمية نمو")
gets AccessError on the Send WhatsApp wizard because P8's
membership-only fix didn't update the `htf_call_center.group_user`
ACL.

**The new model** (locked with user after 3 rounds of clarification):

| Gate | Source | Meaning |
|---|---|---|
| CHANNEL gate | Map Users wizard → `htf.channel.user_ids` (filtered by `lead.team_id == channel.team_id`) | "I'm allowed to work on channel X." |
| LEAD gate | `crm.lead.user_id` (Salesperson field on lead form) | "This specific customer is mine." |
| Both required? | YES — AND intersection | |
| Admin override | `Hatif: Administrator` always sees everything | |

**Files changed** (9 files, 460 +/- 47):

- `models/discuss_channel.py` — `_htf_allowed_member_partner_ids` rewritten for 2-gate (channel-gate via `HtfChannel.search_count` with team match, lead-gate via existing iteration).
- `models/res_users.py` — new `_htf_sync_group_membership()` — idempotent grant/revoke of `Hatif: User` based on whether the user has any active `htf.channel.user_ids` mapping. Never touches admins (their group implies user).
- `models/htf_channel.py` — write/create hooks (`_htf_propagate_access_change`) that:
  - resync group for users added/removed,
  - recompute Discuss channel membership for every customer on the affected team.
- `models/crm_lead.py` — extended `write` hook to also fire on `team_id` change (matters under 2-gate); added `create` hook so a new lead with `user_id` set triggers resync immediately.
- `wizards/map_users.py` — `action_apply` calls `_htf_sync_group_membership()` on every touched user (so a no-op apply still converges drifted state from older installs).
- `tools/prune_htf_discuss_members.py` — `_allowed_partner_ids` now delegates to `discuss.channel._htf_allowed_member_partner_ids` (the single source of truth — no more duplicated logic).
- `migrations/19.0.1.27.0/post-2gate-rebuild.py` — idempotent backfill: grants `Hatif: User` to every user in any active `htf.channel.user_ids`, then recomputes membership on every Hatif Discuss channel.
- `tools/htf_p7_check.py` — new section `[8] 2-gate access` with 9 assertions covering each gate alone, both together, drop/re-add cycles, and the originally-failing wizard-open path (`htf.send.whatsapp.wizard.with_user(agent).check_access('create')`).
- `__manifest__.py` — version bump.

**Regression result**: 303/309 — the 9 new p7 assertions all pass; the same 6 pre-existing failures from session-close yesterday persist (outbound author = customer, call body has phone icon, missed-call body wording, chatter Summary/Recording from DNS-failing cdn.example URL, p2 dispatch-rollback). NONE related to my changes.

### Docs — README install guide rewrite (commits `2fcbfe4` + `cc9f3aa`)

- Pattern: "Quick install — Ubuntu + Docker Compose (Numo's reference layout)" at the TOP with exact paste-sequence using real paths (`/opt/odoo-erp-numo-sa/extra-addons`, `web` container), followed by a "Detailed walkthrough (any layout)" with `/YOUR/ADDONS/PATH` placeholders.
- Critical step that the old README was missing: `pip install --break-system-packages requests phonenumbers` inside the Odoo container. Without it the install hard-crashes at module import (`requests` is the first thing services/http_client.py imports).
- "Updating to a newer version" now has a Numo one-liner (`git pull && docker compose restart web`) followed by the generic any-layout block.
- New "Uninstall" section noting the schema is safe (every `discuss.channel.x_htf_*` field is nullable with `set null` ondelete).

---

## Live state at session close

| Surface | Local DB | erp.amro.pro (prod) |
|---|---|---|
| Module version | 19.0.1.27.0 (manifest + DB) | 19.0.1.26.0 (NEEDS DEPLOY) |
| 2-gate access model | LIVE, 9/9 tests passing | NOT YET LIVE |
| Hatif: User auto-grant | LIVE | NOT YET LIVE |
| All other P0–P8 features | LIVE | LIVE (yesterday) |
| Prune state | clean (verified 0 extras across 6 channels yesterday) | clean (verified 0 extras) |

---

## PENDING ACTIONS for the next session

### 1. ★ Deploy v19.0.1.27.0 to prod (the only blocking item)

```bash
ssh contabo
cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo
git pull origin main
bash htf_call_center/tools/deploy.sh
```

Migration `19.0.1.27.0/post-2gate-rebuild.py` fires automatically on
the version bump. Expect:
- Step 1 log: "syncing Hatif: User group for N distinct user(s) from 1 active channel(s)" — N depends on how many agents you previously mapped in the Map Users wizard. From the screenshot at session start, only 2 agents had "أكاديمية نمو" assigned (Amr Afifi + amro.sa.af@gmail.com), so N=2.
- Step 2 log: "recomputing membership on 6 Hatif Discuss channel(s)" — current member set on prod is `{customer + admin}` per channel; agents added by the 2-gate model would show up here.

### 2. Open the Map Users wizard on prod and finish the mapping

The screenshot at session start showed 5 of 7 Hatif agents with no
Odoo user mapped and no channel assigned. Pick the matching Odoo user
for each + assign "أكاديمية نمو" (or the right channel) for each
sales agent. Click Save. The group + Discuss-membership sync fires
automatically.

### 3. Re-verify in the InPrivate browser

Same session/account that hit the original error: open a lead in
"Numo Academy" team where the InPrivate user is the Salesperson, click
**Send WhatsApp** — expect the wizard to open instead of the
"خطأ في الوصول" dialog. If it works, take a screenshot and we're done.

### 4. THEN return to the original queue choice

The original AskUserQuestion ("which queue item next?") was deferred
behind this fix. Re-ask once the deploy + InPrivate re-test are done.
Options remain:
- P8 with proposed defaults (Outbound Sales Acceleration)
- P9 — Speech Analytics via n8n
- P5 — Conversations Sync
- Send the Hatif support email

---

## Lessons learned this session (sticky)

### Odoo migration loader is silent unless versions differ

`migrations/<version>/post-*.py` ONLY fires when DB-recorded
`latest_version` is strictly less than the manifest version. If you
just bumped 1.26→1.27 and ran the upgrade, the SECOND run won't
re-trigger the migration even with `-u`. To re-test locally:

```sql
UPDATE ir_module_module SET latest_version='19.0.1.26.0' WHERE name='htf_call_center';
```

Then re-upgrade. Run with `--log-level=info` to see
`odoo.modules.migration: module X: Running upgrade [version>] script-name`.
Without that level the migration runs silently and is easy to miss
in casual log scanning.

### Odoo 19 group write API

```python
user.write({'group_ids': [(4, group.id)]})   # add
user.write({'group_ids': [(3, group.id)]})   # remove
```

The field on `res.users` is `group_ids` (NOT `groups_id` which was the
Odoo ≤18 name). Reverse direction: `group.user_ids` (NOT `users`).
Checks: `group in user.group_ids` or `user in group.user_ids` both work.

### Test wizard ACL access without raising

```python
env['htf.send.whatsapp.wizard'].with_user(agent).check_access('create')
```

Raises `AccessError` if denied, returns None if allowed. This is
exactly what we used to assert the regression fix in p7 test [8],
state S5. Avoid catching `Exception` — `check_access` only raises one
specific class so be precise.

### deploy.sh vs UI module upload

For git-deployed modules: deploy.sh wins. UI Import (Apps → ⋮ →
Import Module) is fine for one-off third-party `.zip` drops but
bypasses git (drift), often fails on read-only bind mounts, only
reloads Python on ONE worker (others serve stale code until recycle),
and is hard to log/script. Rollback for git-deployed: `git checkout
<prev sha> && deploy.sh`. Rollback for UI-uploaded: "find the old
zip somewhere".

### Map Users wizard's channel_ids was already there

The Many2many `channel_ids` on `htf.map.users.wizard.line` was added
in v19.0.1.15.0 (commit `57d2b63`). Until v19.0.1.27.0 it only wrote
to `htf.channel.user_ids` — not used as the source of truth for ACL
or membership. The 2-gate redesign promotes it: wizard mapping is NOW
the canonical "who can work this channel" allowlist, and the group +
Discuss membership are derived signals.

### README install pattern: Quick (concrete) + Detailed (generic)

For modules with both a reference deployment AND public installers,
the winning structure is: Prerequisites → "Quick install — [reference
layout]" with real paths + real container names → divider → "Detailed
walkthrough (any layout)" with `/YOUR/ADDONS/PATH` placeholders. Same
pattern for the Updating section. Critical: include the Python deps
step (`requests`, `phonenumbers`) in BOTH paths — without them the
install hard-crashes at module import, and it's the most common
skipped step. Use `pip install --break-system-packages` for Docker
containers on Debian 12 base.

---

## Tools shipped (under `htf_call_center/tools/`) — unchanged from yesterday

| Tool | Purpose |
|---|---|
| `deploy.sh` | Paste-safe wrapper for `git pull && stop web && -u htf_call_center && up -d web`. |
| `diagnose_window.{py,sh}` | Walks a partner's 24h-window state. |
| `merge_duplicate_partners.{py,sh}` | Reparents children + archives duplicate partner records sharing a normalized phone. |
| `prune_htf_discuss_members.{py,sh}` | Removes unauthorised members from existing Hatif Discuss channels. NOW delegates to `discuss.channel._htf_allowed_member_partner_ids` instead of duplicating logic. |
| `htf_e2e_check.py`, `htf_p1..p7_check.py` | Local regression suites. p7 grew from 26 to 35 assertions with the 2-gate section. |

---

## Re-entry sequence (next session)

1. Read this file.
2. Confirm prod is healthy: `curl -I https://erp.amro.pro/web/login`
3. Confirm git is up to date: `cd ~/numo-hatif-odoo && git status && git pull origin main`
4. Run the 7 local suites (expect 303/309):
   ```bash
   for s in e2e p1 p2 p3 p3_ui p4 p7; do
     echo -n "$s: "; python3 ~/numo-hatif-odoo/htf_call_center/tools/htf_${s}_check.py 2>&1 | grep -E "passed|RESULT" | tail -1
   done
   ```
5. **First physical action**: deploy v19.0.1.27.0 to prod (section "PENDING ACTIONS #1" above).
6. After deploy + InPrivate verification, re-ask the queue-choice question.

---

Welcome back. Don't skip THE DRILL (`/Users/amro/Downloads/Claude/odoo-modules/CLAUDE.md`).

— end of NEXT_SESSION.md (clean handoff 2026-05-23, v19.0.1.27.0 on GitHub / pending deploy)
