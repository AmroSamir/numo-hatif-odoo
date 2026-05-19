# P7 Revert Runbook — Discuss / Hatif Mirror

This runbook is the **escape hatch** for the P7 feature: "mirror Hatif
calls + WhatsApp into per-partner Odoo Discuss channels". It is shipped
**before** the feature so that we always have a rollback path ready,
including before merge.

If something is wrong with the mirror — duplicate messages, noisy
notifications, wrong author, infinite loop, perf regression — pick the
**lowest tier** that solves the user-visible problem. Higher tiers are
strictly more destructive and slower to undo. Never start at L5 if L1
would do.

---

## Before you revert — gather these facts (2 minutes)

Do not skip this. Half of "rollback" incidents end up being a single
bad partner row or one stuck cron — and a full L4/L5 revert just hides
the cause.

- [ ] **Which DB?** `odoo`, `test`, or production? Probe with
      `/web/session/get_session_info` or
      `psql -d <db> -c "SELECT name FROM ir_module_module WHERE name='htf_call_center'"`.
- [ ] **Which environment?** Local docker, staging, or `erp.amro.pro`?
- [ ] **What is the user-visible symptom?** Screenshot or recording.
      ("Discuss is slow" vs "every WA message double-posts" → different fixes.)
- [ ] **When did it start?** Correlate against deploy time / cron run /
      recent partner imports.
- [ ] **Scope: one partner, one team, or everyone?**
      `SELECT count(*) FROM discuss_channel WHERE x_htf_partner_id IS NOT NULL;`
- [ ] **Is the master flag actually on?**
      ```bash
      docker exec -i odoo-app odoo shell -d <db> --no-http <<'PY'
      icp = env['ir.config_parameter'].sudo()
      for k in (
          'htf_call_center.discuss_mirror_enabled',
          'htf_call_center.discuss_mirror_inbound',
          'htf_call_center.discuss_mirror_calls',
          'htf_call_center.discuss_outbound_route',
          'htf_call_center.discuss_ui_override',
      ):
          print(k, '=', icp.get_param(k, default=''))
      PY
      ```
- [ ] **What's the queue look like?** Check `mail.message` row counts in
      the last hour and the Hatif webhook event log for retries.
- [ ] **Tell #ops you're rolling back.** Pin the message with tier +
      DB + timestamp.

If after this you still need to revert, walk down the table below.

---

## Tiers at a glance

| Tier | What | Wall time | Reversible? | Destructive? |
|------|------|-----------|-------------|--------------|
| L1   | Toggle master flag `discuss_mirror_enabled = False` | ~30 s | Yes (flip True) | No |
| L2   | Toggle one sub-flag (inbound / calls / outbound / UI) | ~30 s | Yes | No |
| L3   | Run `disable_p7_discuss.py` (flags off + archive channels) | ~2 min | Yes (`enable_p7_discuss.py`) | No |
| L4   | `git revert <merge-sha>` of the P7 PR | ~10 min | Yes (revert the revert) | No (code only) |
| L5   | Run `unbackfill_htf_discuss.py --commit` (delete mirrored messages) | ~5 min | **No** (PG restore only) | **Yes** |

The scripts live in `htf_call_center/tools/`.

---

## L1 — Toggle the master kill-switch (30 s)

**When to use:** Anything user-visible going wrong with the mirror and
you want to stop the bleeding NOW.

```bash
docker exec -i odoo-app odoo shell -d <db> --no-http <<'PY'
env['ir.config_parameter'].sudo().set_param(
    'htf_call_center.discuss_mirror_enabled', 'False')
env.cr.commit()
print('disabled')
PY
```

Effect:
- New inbound WA / call events stop posting to Discuss immediately.
- Existing mirrored channels remain visible (operators can still read them).
- All other Hatif functionality (chatter on res.partner, htf.call, htf.wa.message) keeps working.

Verify: post a test WA inbound and confirm it lands on `res.partner`
chatter but NOT on `discuss.channel`.

Reverse: flip the same key back to `'True'`.

---

## L2 — Toggle a single sub-flag (30 s)

**When to use:** Only one mirrored surface is misbehaving; keep the rest.

| Symptom | Flag to disable |
|---------|----------------|
| Inbound WA double-posts / spams Discuss | `htf_call_center.discuss_mirror_inbound` |
| Call bubbles / voice attachments bad | `htf_call_center.discuss_mirror_calls` |
| Agent replies in Discuss not reaching customer (or duplicating) | `htf_call_center.discuss_outbound_route` |
| OWL ChatWindow broken — call icon weird or button missing | `htf_call_center.discuss_ui_override` |

```bash
docker exec -i odoo-app odoo shell -d <db> --no-http <<'PY'
env['ir.config_parameter'].sudo().set_param(
    'htf_call_center.discuss_mirror_inbound', 'False')   # ← change key
env.cr.commit()
print('sub-flag off')
PY
```

Reverse: flip the same key back to `'True'`.

---

## L3 — Run `disable_p7_discuss.py` (2 min)

**When to use:** L1/L2 didn't fully stop the symptom OR the mirrored
channels themselves are confusing users (e.g. they show stale state)
and you want them off everyone's sidebar without deleting anything.

```bash
cd /Users/amro/numo-hatif-odoo
python3 htf_call_center/tools/disable_p7_discuss.py <db>
```

What it does:
- Sets all 5 feature flags to `False`.
- Archives every `discuss.channel` where `x_htf_partner_id IS NOT NULL`
  (sets `active=False` — rows + messages stay in the DB).
- Idempotent. Safe to run twice.

Verify: refresh Discuss in the browser. Hatif channels should not
appear in the left rail. `psql -c "SELECT count(*) FROM discuss_channel
WHERE x_htf_partner_id IS NOT NULL AND active = TRUE"` should be 0.

Reverse:
```bash
python3 htf_call_center/tools/enable_p7_discuss.py <db>
```

---

## L4 — `git revert` the P7 merge (10 min)

**When to use:** A code-level bug — the mirror is doing the wrong
thing, not just being on/off — and you can't patch forward fast.

1. Find the merge sha:
   ```bash
   cd /Users/amro/numo-hatif-odoo
   git log --oneline --merges --first-parent main | head
   ```
2. Revert it (creates a new commit on `main`, no force-push needed):
   ```bash
   git revert -m 1 <merge-sha>
   git push origin main
   ```
3. On the box, pull + upgrade:
   ```bash
   docker exec odoo-app odoo -d <db> -u htf_call_center \
       --stop-after-init --log-level=warn
   docker compose -f /Users/amro/Downloads/Claude/ai-dnd-builder/odoo-local/docker-compose.yml restart odoo
   sleep 5
   ```
4. Run the L3 cleanup so the now-orphaned mirrored channels disappear:
   ```bash
   python3 htf_call_center/tools/disable_p7_discuss.py <db>
   ```
   (After L4 the flag-reading code is gone, but `ir.config_parameter`
   rows are harmless. The channel-archive part is the useful bit.)

Verify: the P7 menus / UI elements are gone. `htf.call` and
`htf.wa.message` still function. Old chatter on `res.partner` is intact.

Reverse: revert the revert commit, redeploy, then
`python3 htf_call_center/tools/enable_p7_discuss.py <db>`.

---

## L5 — `unbackfill_htf_discuss.py --commit` (5 min) — **DESTRUCTIVE**

**When to use:** Only when the mirrored messages themselves are wrong
in a way reports / search are surfacing — and you've accepted that the
mirrored Discuss history will be permanently gone.

This is the only tier without an in-app reversal. Recovery is a
PostgreSQL backup restore.

```bash
# 1. ALWAYS dry-run first.
python3 htf_call_center/tools/unbackfill_htf_discuss.py <db>
#    ↑ default is --dry-run; prints the per-criterion breakdown.

# 2. If the numbers look right, commit:
python3 htf_call_center/tools/unbackfill_htf_discuss.py <db> --commit
```

What it does:
- Deletes `mail.message` rows tagged as Hatif-mirrored by ANY of:
  - subtype xmlid `htf_call_center.mt_htf_mirror`
  - author = `htf_bot` user's partner (xmlid `htf_call_center.user_htf_bot`,
    or login `htf_bot` if the xmlid is missing)
  - `model = 'discuss.channel'` AND parent channel has `x_htf_partner_id`
- Archives every `discuss.channel` with `x_htf_partner_id`.
- **Explicitly skips** any row whose `model = 'res.partner'` — your
  original chatter history is safe.

Pre-flight:
- [ ] Ran L1 first to stop new mirror writes.
- [ ] Have a recent PG backup. Confirm: `pg_dump <db> | wc -c > /dev/null`.
- [ ] Dry-run output's `safe_to_delete` count looks sane (not 0, not
      millions). Sanity check by hand:
      `psql -c "SELECT count(*) FROM mail_message
               WHERE author_id = (SELECT partner_id FROM res_users WHERE login='htf_bot')"`.

Recovery hint (printed by the script too):
> The original chatter rows on `res.partner` are UNTOUCHED — your real
> Hatif call / WhatsApp history is safe. Only the Discuss-channel
> mirror copies were deleted.

---

## Post-revert checklist (any tier)

After the revert lands:

- [ ] Refresh Discuss in a clean browser session — confirm the mirror
      surface is gone (or healed).
- [ ] Open a real partner: chatter still shows Hatif call + WA messages.
- [ ] Run `htf_e2e_check.py` against the same DB — every non-P7 test
      should still pass.
- [ ] Capture metrics: row counts before vs after, webhook event lag.
- [ ] File an incident note in `htf_call_center/docs/` (`P7_INCIDENT_<date>.md`)
      with: tier used, why, who decided, what we learned, what to fix
      before re-enabling.
- [ ] Decide on re-enable plan: same flags + canary partners only, or
      wait for a follow-up PR.

---

## Quick reference — script locations

| Tier | Script |
|------|--------|
| L3   | `htf_call_center/tools/disable_p7_discuss.py` |
| L3 reverse | `htf_call_center/tools/enable_p7_discuss.py` |
| L5   | `htf_call_center/tools/unbackfill_htf_discuss.py` |

All scripts:
- Take the DB name as the first positional arg.
- Shell out to `docker exec -i odoo-app odoo shell -d <db>` (same
  pattern as `htf_p4_check.py`).
- Print timestamped log lines.
- Are safe to run from the host without an Odoo Python env.
