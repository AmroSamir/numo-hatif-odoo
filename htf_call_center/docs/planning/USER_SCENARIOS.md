# User Scenarios

Narrative walkthroughs that drive design. Each scenario is a single trace through the system from real-world trigger to final state. No partial paths.

---

## S1 — Inbound call from a known lead, agent answers, productive

**Actors:** Sarah (potential parent of student), Reem (sales agent)

1. Sarah calls Numo Academy main line `+966 11 ...`
2. Hatif IVR plays, Sarah picks "Sales"
3. Hatif routes to Reem's queue, Reem's mobile rings on Hatif app, she answers
4. They talk 4m 12s, Sarah confirms interest in "Cambridge Year 8" program
5. Reem hangs up — Hatif fires call webhook to `https://erp.numo.sa/htf/webhook/call`
6. Odoo verifies HMAC, parses payload
7. Caller number `+966 5x xxx` matches `res.partner` ID 142819 (Sarah's existing record)
8. System looks for the most-recent open `crm.lead` linked to partner 142819 + assigned to Reem → finds lead 78321 in stage "New"
9. Creates `htf.call` row with status=Completed, type=Inbound, recordingUrl, transcription (~140 words, 2 speakers), AI summary "Parent inquiring about Cambridge Year 8…", sentiment=Positive
10. Posts a `mail.message` to lead 78321's chatter:
    - 📞 Call answered • 4m 12s • Reem
    - 🎧 Audio player (streaming `recordingUrl`)
    - 📝 Transcript expandable (speakers labeled Agent/User)
    - 🤖 AI Summary card (markdown)
    - 🟢 Sentiment: Positive
    - QA scorecard rubric (criteria from evaluationCriteriaResult)
11. Auto-stage progression: Reem reads message, clicks `Mark Qualified` → lead moves to "Qualified" stage
12. Sentiment trend mini-chart on lead header updates with new positive datapoint

**Acceptance:**
- Webhook → chatter ≤ 10s
- Audio plays without re-fetching token
- Transcript clickable to seek audio
- Lead correctly identified (no orphan call)

---

## S2 — Inbound call to unknown number, missed

**Actors:** Unknown caller, no agents available

1. Call rings, no one answers within Hatif's queue timeout
2. Hatif fires call webhook with status=NoAnswer (5)
3. Odoo finds no matching `res.partner` for callerNumber
4. Auto-create `res.partner` with name=`+966 5x xxx`, phone normalized E.164, `x_htf_contact_id` synced
5. Auto-create `crm.lead`:
   - name = phone (until enriched)
   - team = team owning the channel
   - source = "Hatif Inbound"
   - x_htf_call_id = htf.call ID
6. Auto-create `mail.activity`:
   - type = "Phone Call"
   - assigned to = round-robin agent in team (existing numo_crm logic)
   - deadline = today
   - summary = "Missed call — please call back"
7. Daily digest email next morning includes this missed call under "Yesterday's missed calls"

**Acceptance:**
- Lead has phone, team, source filled
- Activity scheduled for the right user
- Duplicate suppression if same number rings twice in 5 min (uses external_event_id dedup)

---

## S3 — Sarah replies on WhatsApp 2 days later

1. Sarah opens WhatsApp, sees the welcome template Reem sent yesterday, taps "Reply"
2. Sends: "Hi, I'd like to know about fees for Cambridge Year 8"
3. Hatif fires WA webhook to `/htf/webhook/whatsapp`
4. Odoo matches contactId → res.partner 142819 → lead 78321
5. Posts inbound bubble to lead chatter:
    - 💬 Sarah • 14:32
    - "Hi, I'd like to know about fees for Cambridge Year 8"
    - Status: Delivered ✓✓
6. Updates `last_inbound_at` on res.partner — opens 24h Meta window
7. Triggers automation: stage stays "Qualified", but adds activity "Reply about fees"
8. Reem opens the lead, sees the bubble in chatter, types reply directly in chatter composer with "WA" toggle on
9. Reply sent via `/v1/whatsapp/.../sendText` (free — within window)
10. Outbound bubble appears in chatter immediately (optimistic), then status updates ✓ → ✓✓ → ✓✓-blue when read
11. Sentiment trend mini-chart adds another positive node

**Acceptance:**
- 24h-window indicator chip shows 🟢 (free) above composer
- WA toggle defaults remembered per user
- Optimistic UI doesn't show pending state for >2s
- Read receipt updates the existing message, doesn't post a new one

---

## S4 — Reem sends a templated message to a list of 30 fresh leads

1. Reem filters CRM Pipeline: stage=Qualified, last_action older than 3d, assigned to her
2. Selects 30 leads, opens "Action" menu → "Send Hatif WA Template"
3. Wizard:
   - Channel: Numo Academy WA (auto-picked)
   - Template: `cambridge_followup_v2` (manual list — Hatif has no template API, registry is local)
   - Variable mapping:
     - `{{1}}` → `partner.name`
     - `{{2}}` → `lead.x_program_interest`
   - Header: image of brochure (uploaded once, reused)
4. Pre-flight panel:
   - 30 recipients
   - 2 in DNC list — excluded
   - 5 outside 24h window — will use template (Marketing category, $0.024 each)
   - 23 inside window — will use template anyway (template msg always allowed)
   - Total est cost: $0.72
5. Reem clicks "Send"
6. Bridge module loops, sends 28 messages, persists per-recipient `htf.message` rows
7. Progress bar updates live
8. Result table: 27 sent, 1 failed (number invalid)
9. Each lead's chatter gets the outbound template bubble

**Acceptance:**
- DNC respected
- Cost estimate shown before send
- One failure doesn't block others
- Each lead gets exactly one chatter post

---

## S5 — Outbound IVR confirmation campaign

**Setup:** Reem wants to remind 50 students with appointments tomorrow.

1. Reem filters: appointments tomorrow, status=Booked
2. Select all → Action → "Trigger Hatif IVR" → picks config "appointment-confirm" from dropdown
3. Wizard explains: "Each contact will receive an automated call. Press 1 to confirm, 2 to cancel."
4. Reem clicks Run
5. Bridge calls `htf_call_center.services.IvrService.trigger()` for each contact, with externalId = lead UUID
6. Hatif dials each, plays TTS in Arabic ("Press 1 to confirm…"), captures DTMF
7. Per-call IVR webhook arrives:
   - For digit 1 → mark `lead.x_appt_confirmed = True`, append confirmation activity
   - For digit 2 → set `stage_id = lost`, `lost_reason = appt_cancelled`, schedule reschedule call task
   - For NoInput / NotAnswered → mark `lead.x_appt_followup = True`, schedule activity "Manual reminder"
8. Aggregated result on a dashboard tile in numo_crm 3D analytics: "IVR runs today: 50 dialed, 38 confirmed, 7 cancelled, 5 unreachable"

**Acceptance:**
- Each lead gets exactly one IVR run row
- Bridge handles digit → action mapping via documented config dict, not magic strings
- Failed dials don't block subsequent ones
- IVR webhook idempotent (same externalId twice = no duplicate effect)

---

## S6 — Admin onboarding a new agent

1. New agent Aisha joins, gets `res.users` ID 47
2. Admin (Amr) goes to Settings → Hatif → Map Users
3. Wizard pulls live workspace users from Hatif `/v1/workspaces/users`
4. Auto-matches by email — Aisha's `aisha@numo.sa` matches her Hatif user ID
5. Amr clicks Save — `res.users.x_htf_user_id` set on user 47
6. From now on:
   - Aisha's outbound WA messages route to her Hatif user as conversation assignee
   - Inbound calls answered by her Hatif user are attributed to her in Odoo chatter (author_id = Aisha)
   - Record rules let her see only conversations assigned to her in Hatif

**Acceptance:**
- Wizard flags any unmatched Hatif users for manual link
- Auto-suggests email match before saving
- Audit log entry on `res.users` of the mapping
- Re-running the wizard idempotent (no duplicate links)

---

## S7 — Customer opts out of WhatsApp marketing

1. Customer Khaled receives a marketing WA template
2. He replies: "STOP" or "إلغاء الاشتراك"
3. Inbound WA webhook → bridge module's listener sees text matches DNC keyword pattern
4. Auto-create `htf.dnc` row with phone=Khaled's, captured_keyword="STOP", source=automatic
5. Auto-set `res.partner.x_htf_opted_out = True`
6. Future outbound WA send pre-check fails for this number with clear toast: "Number is in DNC list (auto-opted out 2026-05-12)"
7. Daily digest to admin: "1 new opt-out today: Khaled +966..."

**Acceptance:**
- Keyword list configurable (Arabic + English)
- DNC blocks template AND text sends
- Manual override only by admin (audit logged)

---

## S8 — Admin onboarding a new htf channel

1. Hatif team provisions a new WA channel for Cambridge brand
2. Amr opens Settings → Hatif → Channels → Sync now
3. Module calls `/v1/channels/service-account` and upserts channels
4. New channel "Cambridge WA" appears, Amr assigns it to team "Cambridge Sales"
5. WA composer for leads belonging to Cambridge team auto-defaults to that channel

**Acceptance:**
- Sync is idempotent
- Channels removed remotely → marked archived locally (not deleted)
- Each team can have a default channel

---

## S9 — Hatif token expired mid-day

1. Aisha tries to send a WA from a lead
2. Bridge calls vendor wrapper → wrapper checks token cache → expired
3. Wrapper auto-refreshes via `/connect/token`
4. Retries the send → succeeds
5. Aisha sees no error

**Acceptance:**
- Refresh transparent
- Retry budget = 1 (avoid infinite loop)
- If refresh itself fails → clear admin alert, surface to user as actionable error
- Token cached in `ir.config_parameter` with expiry timestamp, not memory

---

## S10 — Webhook spoofed payload

1. Attacker discovers `/htf/webhook/call` URL
2. Sends crafted JSON pretending to be Hatif
3. HMAC signature missing or wrong
4. Controller returns 401 immediately, logs warning
5. No DB writes, no chatter posts

**Acceptance:**
- HMAC required — never disabled in prod
- Failed signature logged with IP for monitoring
- Repeated failures from same IP → alert admin
- Replay attacks blocked via timestamp window (±5 min)

---

## S11 — Hatif outage during outbound WA send

1. Reem sends WA to lead
2. Vendor wrapper attempts POST → connection error
3. Retries 3 times with exponential backoff (1s, 2s, 4s)
4. All fail
5. Surfaces error toast: "Hatif unreachable, message NOT sent"
6. Persists `htf.message` row with state=`failed_pending` so admin can replay
7. Cron job retries `failed_pending` messages every 5 min for up to 30 min, then marks `failed_final`
8. Final failure → notification to admin + user

**Acceptance:**
- User sees clear error state, not a silent failure
- No duplicate sends if user retries manually
- Admin can see a "Failed sends" admin view

---

## S11.5 — Multi-channel team binding

**Setup:** Numo has 5+ Hatif channels:
- `+966 11 500 1591` Main → Numo Academy Sales team
- `+966 11 500 1592` Secondary → Cambridge KSA team
- `+966 11 500 1593` → NH School team
- `+966 11 500 1594` → Numo Academy Marketing
- `+966 11 500 1595` WA-only → Cambridge WA channel

**Scenarios this design covers:**

1. **Inbound call to 1591** → matches channel "Numo Academy Main" → team "Numo Academy Sales" → auto-created lead inherits team → routed to team's lead_owner OR round_robin agent
2. **Agent on Cambridge KSA team sends WA from a lead** → channel resolver picks Cambridge WA channel (1595) automatically — agent doesn't pick channel manually
3. **Same agent transferred to Numo Academy team next month** → her outbound now defaults to 1591 — zero code change, just team membership update
4. **New brand "NH School Riyadh" launches with new number** → admin syncs channels (button), assigns new channel to "NH Riyadh" team via wizard, done — no module redeploy
5. **One team uses two channels (overflow)** → assign both to team, mark one `default_for_outbound_wa`, the other available via dropdown override on lead form
6. **Channel temporarily disabled by Hatif** → cron sync marks `state=archived`, outbound resolver skips it, falls through to next in chain

**Acceptance:**
- Channel ↔ Team binding done via single wizard (no XML edits)
- Default-channel resolution chain documented + tested
- Agent never picks channel manually unless they want to override
- Adding a 6th channel = sync + 1 dropdown click

---

## S12 — Customer journey across channels (omnichannel coherence)

1. Day 1: Sarah opens website, fills Numo lead form → numo_crm creates lead
2. Day 1+1h: numo_crm classify wizard fires WA template "welcome-academy" via htf
3. Day 2: Sarah replies on WA — chatter post, inbound
4. Day 3: Reem calls Sarah — call webhook posts to chatter
5. Day 4: Sarah misses Reem's follow-up call — missed-call activity
6. Day 5: Sarah replies WA again — bubble + activity completed
7. Day 7: Reem sends WA template "fees-info" inside 24h window — free
8. Day 8: Sarah confirms enrolment — Reem moves to Won
9. On Won: bridge fires WA template "thanks-onboarding" + cancels any pending IVR

**Lead form chatter timeline (one continuous stream):**
- 📝 Lead created (web form)
- 💬 WA template sent (welcome-academy)
- 💬 Inbound WA from Sarah
- 📞 Outbound call (4m, positive sentiment)
- ⏰ Activity completed: "Mark Qualified"
- 📞 Missed call (auto-activity created)
- 💬 Inbound WA
- 💬 Outbound WA (fees-info)
- 🏆 Lead won
- 💬 WA template sent (thanks-onboarding)

**Acceptance:**
- All events on the same lead chatter, chronological
- No event duplicated across channels
- Sentiment trend chart shows the arc
- Won/lost hooks fire exactly once
