# NEXT SESSION — start here

Last updated: **2026-05-25** (end of session)

This session built the **Discuss-first WhatsApp UX** and chased a long
chain of root-cause bugs through to v19.0.1.49.0. All shipped to GitHub
AND deployed to **staging** (erp.amro.pro). NOT yet on prod (erp.numo.sa).

GitHub: https://github.com/AmroSamir/numo-hatif-odoo — branch `main`
HEAD: `0e26d1a` · Module version: **19.0.1.49.0**

---

## ENVIRONMENTS

- **Canonical source:** `/Users/amro/numo-hatif-odoo/htf_call_center`
- **LOCAL dev:** container `web-numo-local`, DB `odoo19_local`, host extra-addons
  `/Users/amro/odoo19/stack/extra-addons`. Workflow: edit canonical → rsync to
  local extra-addons → `docker exec web-numo-local odoo -d odoo19_local -u htf_call_center --stop-after-init --no-http` → `docker restart web-numo-local`.
- **STAGING:** SSH alias `contabo` (root@84.247.189.212, key `~/.ssh/contabo_vps`, host `vmi3095315`).
  Path `/opt/odoo-erp-amro-pro`, container `web-erp-amro-pro`, DB **`numo`**, db container `db-erp-amro-pro`. URL https://erp.amro.pro.
  Deploy one-liner:
  ```
  ssh contabo 'cd /opt/odoo-erp-amro-pro/extra-addons/numo-hatif-odoo && git pull origin main && cd /opt/odoo-erp-amro-pro && docker compose stop web && docker compose run --rm web odoo -d numo --i18n-overwrite -u htf_call_center --stop-after-init --no-http && docker compose up -d web'
  ```
- **PROD:** erp.numo.sa (`/opt/odoo-erp-numo-sa`). ⚠️ ONE Hatif workspace = ONE webhook URL,
  so staging + prod share the same Hatif channels; inbound webhooks can only go to ONE Odoo
  (currently amro.pro). Hatif source IP `8.213.48.16`.

### Running odoo shell via SSH (paste-indent breaks heredocs)
Write probe to `/tmp/x.py` locally → `scp -q /tmp/x.py contabo:/tmp/x.py` →
`ssh contabo 'docker cp /tmp/x.py web-erp-amro-pro:/tmp/x.py && docker exec -i web-erp-amro-pro odoo shell -d numo --no-http < /tmp/x.py 2>/dev/null'`.

---

## THE FEATURE (Option C)

WhatsApp buttons (partner form, lead form, `htf_phone` widget) open the per-partner
**Hatif Discuss chat popup** instead of the Send wizard. Composer disables free-form text
when Meta's 24h window is closed and shows an in-banner teal **"Send Template"** button
(→ existing wizard, template mode). Window open → free-chat.

Toggle: `htf.config.whatsapp_button_opens_discuss` (default True; migration 19.0.1.35.0).
It's a RUNTIME OVERRIDE in `htf.config.discuss_mirror_active()` — True forces all 4
discuss-mirror sub-flags active without mutating stored values.

Key files: `models/res_partner.py:action_htf_open_whatsapp()`, `models/crm_lead.py:action_htf_open_whatsapp()`,
`static/src/discuss/open_chat_action.js`, `composer_patch.js`, `composer_banner.xml`,
`htf_composer.scss`, `thread_model_patch.js`.

---

## BUG-FIX CHAIN (the "why")

- **v37** outbound mirror also fires from `_post_chatter_and_fire` (wizard sends show in discuss).
- **v38** render template body from `htf.template.body_preview` (was "Attachment/welcom_message").
- **v39** wizard `action_send` → `act_window_close` (was redirecting to htf.message form).
- **v40** `discuss.channel.x_htf_last_inbound_at` field + `_htf_stamp_inbound_now()` (writes + bus push
  `Store(bus_channel=self).add(...).bus_send()`). `windowOpen` reads it. **Dup-partner-proof.**
  Migration 19.0.1.40.0 backfills. Root cause: DUPLICATE PARTNER RECORDS (same phone, 2 rows).
- **v41** discuss route passes `channel=self.x_htf_last_htf_channel_id` to `send_text` (was re-resolving via team-default → `HtfChannelNotFoundError`).
- **v42** discuss route gates window on CHANNEL timestamp; `send_text` gains `skip_window_check`.
- **v44** `htf.outbound.dedup` model + `_htf_claim_send()` AUTONOMOUS-cursor committed claim BEFORE the slow HTTP → stops duplicate sends from websocket-reconnect resend storms (customer got same msg 5×). xact advisory lock (v43) FAILED — resends are sequential not concurrent. 90s window.
- **v45** `skip_discuss_mirror` flag (no 2nd OdooBot bubble) + unlink resend bubble on failed claim → one bubble per send.
- **v46** inbound `_find_partner_by_hatif_contact_phone` uses `regexp_replace(phone,'\D','','g')=digits` + last-9-digit tail. Was `('phone','ilike',digits)` → MISSED spaced phones "+966 56 692 5142" → created duplicate placeholder partner.
- **v47** `action_htf_open_whatsapp` calls `conversations.refresh_window_from_hatif(partner, channel)` on chat-open; falls back to `lookup_latest_conversation_id(phone)`. Hatif = source of truth for the 24h window.
- **v48 CRITICAL** Hatif conversations/timeline API returns **lowercase** keys (`items/direction/creationTime/id/lastActivityAt`); code read PascalCase → `get_latest_inbound_at` + `lookup_latest_conversation_id` ALWAYS returned None. `direction:1`=customer INBOUND, `direction:2`=outbound. Working endpoints: `GET /v2/conversations/service-account/channels/{channelId}?PhoneNumber=<e164>&Sorting=LastActivityAt DESC` and `GET /v2/conversations/service-account/{convId}/timeline`.
- **v49** `_lookup_latest_conversation(env,e164)` returns `(conv_id, htf_channel)`; refresh records `x_htf_last_htf_channel_id` on chat-open so the reply routes (closes v41 gap).

---

## KEY LEARNINGS

1. Config params set via `odoo shell` DON'T invalidate the running web workers' ormcache — `docker compose restart web` after shell config changes. Settings-UI changes invalidate immediately.
2. DRY-RUN: `allow_real_outbound` + `outbound_phone_whitelist`. Non-empty whitelist = only listed numbers real, rest dry-run (event id "dryrun:"). Currently: `allow_real_outbound=True`, whitelist EMPTY (all real).
3. `--i18n-overwrite` REQUIRED on upgrade when a translatable source string changed, else stale ar stays mapped to old source → English shows.
4. OWL Composer: `inputClasses` is a template-local var (t-set), NOT a property — can't patch as getter. Use `isSendButtonDisabled` + template-injected class. Composer actions render ICON-ONLY → prominent button goes inside the banner via t-inherit.
5. Odoo 19 mail.message OWL field is `author_id` (res.partner relation), not `author`.
6. `ir.config_parameter.set_param('')` DELETES the row → get_param falls back to schema default.
7. DUPLICATE PARTNERS are the recurring villain. All window/channel/send logic keys on the CHANNEL, not the partner.

---

## OUTSTANDING / DO NEXT

1. **PENDING USER VERIFICATION (cold-start test):** adam test partner **101718**, phone `+966 56 692 5142`,
   live Hatif conversation `3a216e25-1703-ba02-691e-d7949fb20c2d` on channel `3a20ffce-cc80-7229-8300-a394d13725a4` (أكاديمية نمو).
   adam was just un-stamped (cold, no local data). User clicks Send WhatsApp → expect composer
   auto-opens (window resolved from Hatif by phone, v48), reply sends once (v44) and routes (v49).
2. **welcom_message template body_preview is EMPTY** (htf.template id 2) → renders "Attachment/welcom_message".
   User must paste approved Meta body. Real text: "حياك الله، شفت تسجيلك بالنظام وودي اشوف اذا عندك اي سؤال او استفسار حنا جاهزين / أكاديمية نمو".
3. **Websocket "Real-time connection lost"** on staging — Odoo bus error `KeyError:'socket'` at
   `bus/websocket.py:1014`. Nginx /websocket config is CORRECT. It's an Odoo worker/gevent config
   issue (environmental, not the module). Triggers the resend storms (now defended). Check odoo.conf workers/gevent.
4. Parked (composer_patch.js header): mobile composer untested; no inline template picker; no "X hours left" badge (needs stored `x_htf_window_closes_at`).
5. De-dupe the test partners sharing one phone (data hygiene).

---

## TEST DATA on staging (DB numo)

- Team "numo academy" id 45 (note: a capitalized "Numo Academy" team also exists; channel أكاديمية نمو is bound to "Numo Academy"). Leaders: NUMO ACADEMY LEADER (uid 90), NUMO ACADEMY LEADER 2 (uid 91). All pwd `admin`.
- Agents SAL AGN 1/2/3 (uids 87/88/89, `sal.agn.{1,2,3}@numo.test`, pwd `admin`), groups sale_salesman + htf group_user.
- 6 opportunities ids 5812-5817 (2/agent, stage New, dummy phones +9665000000XX).
- adam test partner 101718 (real test number).
- Hatif: 2 channels, 1 template (welcom_message, empty body_preview), 7 user.link mappings. `dev_mode_skip_hmac=True`. `allow_real_outbound=True`, whitelist empty.
- Arabic (ar_001) fully translated incl. app/menu name "Hatif"→"هاتف". ar.po ~267 unique msgids.
