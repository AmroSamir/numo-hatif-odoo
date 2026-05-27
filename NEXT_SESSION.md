# NEXT SESSION — start here

Last updated: **2026-05-27** (end of session 2)

GitHub: https://github.com/AmroSamir/numo-hatif-odoo — branch `main`
Module version: **19.0.1.68.0** (deployed to BOTH staging AND prod).

## SESSION 2 (2026-05-25→27): v50–v68 + PROD GO-LIVE

Fixed a long chain of WhatsApp/call bugs and **deployed to production
(erp.numo.sa) for the first time**. Highlights:

- **v50** — inbound WA webhook crashed on Odoo-19-removed `res.partner.mobile`
  column in `whatsapp_inbound._find_partner_by_hatif_contact_phone`. Inbound
  never landed; outbound (different path) kept working. Use `phone` +
  `phone_sanitized`.
- **WEBSOCKET (infra, not module):** with `workers>0` Odoo serves websockets
  on the **gevent port 8072**, but nginx routed `/websocket`→8069 and the
  container only published 8069 → "Real-time connection lost" + ⚠️ on
  composer sends. Fix = nginx `/websocket`→`127.0.0.1:8072` + publish 8072 +
  restart/reload. **Staging fixed. PROD already publishes 8072 — still verify
  its nginx `/websocket` points to 8072 (workers=12).**
- **v51** — dedupe outbound STATUS webhooks by `conversationEventId` (was
  creating a row+OdooBot bubble per Pending/Read event).
- **v52** — composer Hatif send DEFERRED to a `cr.postcommit` hook (was
  synchronous inside message_post → raced the echo webhook on the same
  discuss.channel row → SerializationFailure → retry suppressed by the
  autonomous dedup claim → agent bubble dropped + re-mirrored as OdooBot).
  Split `whatsapp._send` → `_create_pending_row` + `_dispatch_row`; added
  `prepare_text_send` + `dispatch_prepared`.
- **v53** — reconcile the echo webhook to the composer's row by channel+body
  (echo can arrive before the post-commit hook commits wamid/conv_event_id).
- **v55** — call bubble UPDATES in place as the call progresses (was frozen
  at ringing). `_update_call_bubble` + bus push.
- **v56** — call recording rendered as a Discuss VOICE message. Odoo 19 needs
  a `discuss.voice.metadata` row (mail.message has no voice_ids); message_post
  `{'voice':True}` is IGNORED. Mimetype is `audio/wav` (Hatif), not mp3.
- **v57** — render the FULL Hatif AI summary (### headings + ∙ bullets +
  spacing), no 200-char truncation.
- **v58** — call bubble first line shows DIRECTION (inbound/outbound/missed)
  with colour-coded icon; was generic "Call ended". Arabic verbs in ar.po.
- **v59** — unmapped human agent no longer mislabelled IVR. `_compute_pickup_kind`
  classifies `human` when handler_user_id OR hatif_user_name and not is_ai_call.
- **v60/v61 — PRIVACY:** per-customer Discuss channels were `channel_type='channel'`
  (PUBLIC, joinable by any agent → everyone saw every chat). Now `channel_type='group'`
  (private). Access rule = customer + lead salesperson (the agent who
  contacted) + that agent's OWN team leader + Sales Managers who DON'T lead a
  different team. Migrations 60 (SQL flip to group + resync) / 61 (resync).
  `_htf_allowed_member_partner_ids` + `_htf_sync_channel_members` (CRM-lead
  write/create hook re-syncs on (re)assignment). channel_type can't change via
  ORM → migration uses SQL.
- **v62/v63 — Conversation tab:** read-only WA+call timeline on the CRM lead
  form (`crm_lead.x_htf_conversation_html`, sanitize=False), gated on channel
  membership (`x_htf_can_view_conversation`) so it respects the same privacy.
  Recording as `<audio>` via /web/content + access_token. Scoped `<style>`
  with `!important` resets (Odoo editor injects block margins).
- **v64/v65/v66 — i18n + UX:** translate Conversation/Reply on WhatsApp/Send
  WhatsApp (Send WhatsApp needed the inherit-view reference added to its po
  entry); removed RTL-wrong `justify-content`; date separators (Today/Yesterday/
  localized) in the timeline.
- **v67/v68 — the "agent sent into a closed window" chain (3 bugs):**
  - **A** Hatif's `/v2/conversations` **PhoneNumber filter is IGNORED** — it
    returns the channel's most-recent conversations for ANY number. We took
    items[0] → grabbed an UNRELATED customer's conversation, whose recent
    inbound wrongly opened the window (also a cross-customer read). Fix:
    phone-match ourselves; `refresh_window_from_hatif` LEADS with the
    phone-matched lookup (not the stale cached `x_htf_last_conversation_id`)
    and is FAIL-CLOSED (no match/no inbound → clear the channel stamp).
  - **B** failed post-commit send left the bubble looking delivered → now
    prepend a red "Not delivered" banner.
  - **C** outbound uses the shared service account → any user could send.
    Now require `htf.user.link` (mapped Hatif user) or block.

### Known / open
- **Outbound calls have no recording/summary from Hatif** — verified: the
  webhook payload arrives with `recordingUrl=None, summary=''`. Inbound calls
  get both. This is HATIF-SIDE (outbound recording/summary not produced/enabled),
  NOT an Odoo bug. Check Hatif portal + outbound-recording setting.
- **PROD nginx `/websocket`→8072** — verify (workers=12; 8072 already published).
- **Webhook URL** — ONE Hatif workspace = ONE webhook. Prod is now receiving
  inbound (live WA + calls confirmed), so it appears to be the live target now;
  confirm staging vs prod intent.

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
- **PROD:** erp.numo.sa — SEPARATE VM `ubuntu@web-vm` (NOT reachable from the
  contabo box; deploy commands must be run on web-vm by the user). Path
  `/opt/odoo-erp-numo-sa`, web container `web-erp-numo-sa`, db `db-erp-numo-sa`,
  DB **`numo`**, `workers = 12`, `proxy_mode = True`. `htf_call_center` is a
  symlink → `numo-hatif-odoo/htf_call_center` (git pull updates it). 8069 + 8072
  both published. **Now LIVE on v68** (deployed 2026-05-25). Real outbound
  ENABLED (`htf.config.allow_real_outbound=True`, empty whitelist = all dests).
  Hatif AUTH OK, channels أكاديمية نمو + الدعم الفني mapped.
  Deploy (run ON web-vm; mind heredoc indentation):
  ```
  cd /opt/odoo-erp-numo-sa/extra-addons/numo-hatif-odoo && git pull origin main
  cd /opt/odoo-erp-numo-sa && docker compose run --rm web odoo -d numo --i18n-overwrite -u htf_call_center --stop-after-init --no-http --log-level=warn && docker compose up -d web
  ```
  ⚠️ ONE Hatif workspace = ONE webhook URL. Hatif source IP `8.213.48.16`.

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
