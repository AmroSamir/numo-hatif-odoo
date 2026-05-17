# Data Model

Every model + every field. Source of truth for migrations, tests, and views.

---

## Conventions

- All vendor-side ID columns are `Char(40)` (UUID) — never int FK to vendor
- All E.164 numbers stored as `Char(20)`
- Vendor enums stored as `Selection` mapped to human-readable strings
- All datetimes stored as UTC; UI converts to user's tz
- `state` fields on transient operations: `pending`, `sent`, `delivered`, `read`, `failed`
- Active = True default on every parent model
- **Every model defines `_name`, `_description`, and `_order`** (Odoo 19 best practice — emits warnings otherwise)
- Custom fields on existing Odoo models use `x_htf_*` prefix (locked naming convention)
- Field renames after first ship require explicit migration script (see DEPLOYMENT.md)

## Chatter strategy

- `htf.call`, `htf.message`, `htf.conversation`, `htf.ivr.run` do **NOT** inherit `mail.thread`. They are pure data records.
- Chatter posts live on `res.partner` and `crm.lead` (which already inherit `mail.thread`).
- `htf.call.chatter_message_id` and `htf.message.chatter_message_id` are Many2one back-refs to the `mail.message` post for that record.
- State transition audit on htf.* records uses standard Odoo `_log_access = True` (creator/writer/dates) plus dedicated audit fields (`opened_at`, `closed_at`, etc.) where audit is critical (`htf.call`, `htf.message.template`, `htf.dnc`).
- Bridge handlers post to res.partner / crm.lead chatter, NOT to htf.* records.

## Translations

- All user-visible strings via Odoo's `_()` translation function
- `i18n/en.po` (default English) + `i18n/ar.po` (Arabic, RTL)
- View labels, selection values, error messages, mail.template subjects all translated
- Chatter post bodies use `mail.template` records with translation per language
- Brand name "Hatif" is NOT translated (proper noun)
- Demo data is bilingual where it appears in UAT scripts

## Cron jobs (full list across phases)

| Cron | Phase | Interval | Idempotent | Purpose |
|---|---|---|---|---|
| `htf.cron.refresh_token` | P0 | 30 min | yes | refresh OAuth token if < 5 min to expiry |
| `htf.cron.sync_channels_nightly` | P1 | nightly 02:00 | yes | refresh channel list from Hatif |
| `htf.cron.poll_contacts` | P1 | 30 min | yes | incremental contact pull |
| `htf.cron.poll_conversations` | P6 | 15 min | yes | per-channel conversation + timeline pull |
| `htf.cron.retry_failed_messages` | P3 | 5 min | yes | retry `failed_pending` WA messages up to 30 min |
| `htf.cron.purge_webhook_events` | P0 | nightly 03:00 | yes | archive `htf.webhook.event` rows older than 90 days |
| `htf.cron.refresh_sentiment_history` | P7 | hourly | yes | rebuild `lead.x_htf_sentiment_history_json` from htf.call rows |
| `numo_crm_htf.cron.daily_digest` | P7 | daily 08:00 | yes | per-user email digest |
| `numo_crm_htf.cron.won_back` | P8 | daily 09:00 | yes | 30/60/90d win-back sends |
| `numo_crm_htf.cron.daily_cost_summary` | P8 | daily 23:50 | yes | aggregate WA cost by category |

## Migration policy per phase

- P0 / P0.5: greenfield — no migration scripts
- P1: introduces res.partner.x_htf_* + res.users.x_htf_user_id — pre-migration NOT needed (additive)
- P2–P6: additive only — no migration script unless explicit field rename happens (none planned)
- P7: introduces crm.lead.x_htf_* — additive
- P8: model additions + field additions — additive
- Any future field rename or type change → write `migrations/19.0.X.Y.Z/pre-migration.py` + rollback in `post-migration.py`. Documented per phase if applicable.

---

## Module: `htf_call_center`

### htf.config (singleton, ir.config_parameter wrapper)
| Field | Type | Notes |
|---|---|---|
| client_id | Char | encrypted via fields.Char(groups='htf_call_center.group_admin') |
| client_secret | Char | encrypted, write-only after save |
| base_url | Char | default `https://api.voxa.sa` |
| scope | Char | default `VoxaAPI` |
| webhook_secret_current | Char | current HMAC secret |
| webhook_secret_previous | Char | for rotation |
| token_cache | Char | cached access_token |
| token_expires_at | Datetime | |
| poll_contacts_interval_min | Integer | default 30 |
| poll_conversations_interval_min | Integer | default 15 |
| default_voice | Selection [Male, Female] | TTS default |
| timezone_offset_for_filters | Char | default `+03:00` |
| debug_log_enabled | Boolean | default False |

### htf.channel
| Field | Type | Notes |
|---|---|---|
| name | Char | from Hatif |
| display_name | Char | admin-editable friendly label (e.g. "Cambridge Sales", "Numo Academy KSA") |
| htf_channel_id | Char(uuid) | unique |
| channel_type | Selection [phone, whatsapp, both] | from int 1/2/3 |
| phone_number | Char(20) | E.164 |
| icon | Char | optional |
| team_id | Many2one('crm.team') | **PRIMARY OWNER** — sales team this channel belongs to |
| user_ids | Many2many('res.users') | optional override list of agents allowed to use this channel (default = team members) |
| default_for_outbound_wa | Boolean | per-team, not per-workspace |
| default_for_outbound_call | Boolean | per-team, not per-workspace |
| brand | Char | optional brand label (Cambridge / NH / Numo Academy) for reporting |
| color | Integer | Odoo standard for kanban tagging |
| sequence | Integer | manual ordering in admin |
| state | Selection [active, archived] | |
| last_synced_at | Datetime | |
| notes | Text | admin notes (e.g. "Cambridge KSA inbound only") |
| _sql_constraints | unique htf_channel_id | |
| _sql_constraints | one default_for_outbound_wa per team_id (partial idx) | |
| _sql_constraints | one default_for_outbound_call per team_id (partial idx) | |

### htf.tag
| Field | Type | Notes |
|---|---|---|
| name | Char | |
| htf_tag_id | Char(uuid) | unique |
| icon | Char | |
| description | Text | |
| is_pinned | Boolean | |
| color | Integer | Odoo standard |
| created_at | Datetime | |

### htf.contact.link
| Field | Type | Notes |
|---|---|---|
| partner_id | Many2one('res.partner', required, ondelete='cascade') | |
| htf_contact_id | Char(uuid) | unique |
| last_synced_at | Datetime | |
| sync_state | Selection [synced, pending, error] | |
| custom_properties_json | Text | snapshot of vendor custom properties |

### htf.user.link
| Field | Type | Notes |
|---|---|---|
| user_id | Many2one('res.users', required) | |
| htf_user_id | Char(uuid) | unique |
| email | Char | from Hatif |
| display_name | Char | |
| is_ai_agent | Boolean | |
| role | Selection [owner, member] | |
| last_synced_at | Datetime | |

### htf.conversation
| Field | Type | Notes |
|---|---|---|
| name | Char | computed display name |
| htf_conversation_id | Char(uuid) | unique |
| status | Selection [open, closed] | |
| sentiment_score | Integer | nullable |
| last_activity_at | Datetime | |
| partner_id | Many2one('res.partner') | |
| lead_id | Many2one('crm.lead') | best-match resolved by bridge |
| channel_id | Many2one('htf.channel') | |
| assignee_user_id | Many2one('res.users') | resolved from htf user link |
| assignee_ai_agent_id | Char(uuid) | nullable |
| is_ai_assignee | Boolean | |
| tags | Many2many('htf.tag') | |
| unread_count | Integer | always 0 for service account |
| last_event_source_type | Selection [call, whatsapp, assignation] | |
| last_event_direction | Selection [inbound, outbound, internal] | |
| last_event_status | Char | |
| last_event_preview | Text | |
| events_count | Integer | |

### htf.conversation.event
| Field | Type | Notes |
|---|---|---|
| conversation_id | Many2one('htf.conversation', cascade) | |
| event_id | Char(uuid) | unique |
| source_type | Selection [call, whatsapp, assignation] | |
| source_id | Char(uuid) | call ID or message ID |
| direction | Selection [inbound, outbound, internal] | |
| occurred_at | Datetime | |
| status | Char | |
| body | Text | |
| handler_user_id | Many2one('res.users') | resolved |
| ai_agent_id | Char(uuid) | |
| duration_seconds | Integer | |
| ringing_seconds | Integer | |
| attachment_url | Char | |
| ai_summary_text | Text | |
| transcription_text | Text | |
| reply_to_event_id | Char(uuid) | |
| internal_thread_resolved | Boolean | |
| internal_thread_messages | Integer | |
| location_lat | Float | |
| location_lon | Float | |
| location_name | Char | |
| location_address | Char | |
| assignation_assigned_user_id | Many2one('res.users') | |
| assignation_assigned_ai_agent_id | Char(uuid) | |
| assignation_assigned_by_user_id | Many2one('res.users') | |

### htf.call
| Field | Type | Notes |
|---|---|---|
| name | Char | computed: `[Inbound] +966… → +966…` |
| htf_call_id | Char(uuid) | unique |
| direction | Selection [inbound, outbound] | from int 1/2 |
| status | Selection [active, completed, missed, rejected_caller, rejected_callee, no_answer, cancelled, failed] | from int 0–7 |
| caller_number | Char(20) | E.164 |
| callee_number | Char(20) | E.164 |
| pickup_at | Datetime | |
| hangup_at | Datetime | |
| duration_seconds | Integer | computed from callLength |
| handler_user_id | Many2one('res.users') | resolved from userId |
| ai_agent_id | Char(uuid) | |
| recording_url | Char | |
| transcription_text | Text | |
| transcription_words_json | Text | full word-level timing |
| ai_summary | Text | |
| sentiment | Selection [positive, neutral, negative, mixed, unknown] | from int 1–5 |
| evaluation_criteria_json | Text | array of {id, dataType, description, value, rationale} |
| partner_id | Many2one('res.partner') | resolved by phone match |
| lead_id | Many2one('crm.lead') | resolved by bridge |
| channel_id | Many2one('htf.channel') | |
| chatter_message_id | Many2one('mail.message') | back-ref to chatter post |
| created_at | Datetime | from creationTime |
| _sql_constraints | unique htf_call_id | dedup |

### htf.message (WhatsApp)
| Field | Type | Notes |
|---|---|---|
| name | Char | computed |
| htf_message_id | Char(uuid) | unique (Meta-side) |
| conversation_event_id | Char(uuid) | from sendTemplate response |
| direction | Selection [inbound, outbound] | |
| message_type | Selection [text, image, video, audio, document, location, contact, sticker, template, interactive] | |
| body | Text | |
| media_url | Char | |
| mime_type | Char | |
| state | Selection [pending, sent, delivered, read, failed, failed_pending, failed_final] | |
| error_code | Integer | |
| error_reason | Char | |
| sender_user_id | Many2one('res.users') | resolved |
| latitude | Float | |
| longitude | Float | |
| is_billable | Boolean | |
| meta_category | Selection [marketing, utility, authentication, service] | for cost tracking |
| meta_cost_estimate | Float | local estimate (Hatif doesn't expose) |
| partner_id | Many2one('res.partner') | |
| lead_id | Many2one('crm.lead') | resolved by bridge |
| channel_id | Many2one('htf.channel') | |
| conversation_id | Many2one('htf.conversation') | |
| chatter_message_id | Many2one('mail.message') | |
| created_at | Datetime | |
| _sql_constraints | unique htf_message_id (when not null) | |

### htf.message.template
| Field | Type | Notes |
|---|---|---|
| template_name | Char | template name as registered with Meta (avoid shadowing Odoo's auto `display_name`) |
| display_label | Char | human-readable label |
| description | Text | |
| language | Char(10) | e.g. `ar`, `en` |
| category | Selection [marketing, utility, authentication] | |
| channel_ids | Many2many('htf.channel') | which channels this template is approved on |
| header_type | Selection [none, text, image, video, document] | |
| body_variables_count | Integer | how many `{{1}}` `{{2}}` exist |
| body_variable_labels | Text | JSON dict {1: "name", 2: "program"} |
| buttons_json | Text | JSON describing each button (subType, index, label, dynamic_part) |
| sample_payload_json | Text | for preview |
| state | Selection [draft, approved, paused, deleted] | |
| approved_at | Datetime | |
| created_at | Datetime | |

### htf.ivr.run
| Field | Type | Notes |
|---|---|---|
| name | Char | computed |
| htf_ivr_id | Char(uuid) | unique |
| external_id | Char | from our request, idempotency key |
| destination_number | Char(20) | E.164 |
| channel_id | Many2one('htf.channel') | |
| config_key | Char | which IVR script (e.g. `appointment-confirm`) |
| status | Selection [pending, initiated, ringing, in_progress, completed, no_answer, busy, failed] | |
| result | Selection [none, digit_pressed, no_input, invalid_input, not_answered, destination_busy, technical_failure, cancelled] | |
| pressed_digit | Char(2) | |
| call_duration_seconds | Integer | |
| hangup_cause | Char | |
| error_message | Char | |
| webhook_url | Char | |
| audio_file_url | Char | |
| tts_text | Text | |
| tts_voice | Selection [male, female] | |
| max_audio_retries | Integer | |
| input_timeout_ms | Integer | |
| digit_timeout_ms | Integer | |
| webhook_received_at | Datetime | |
| partner_id | Many2one('res.partner') | |
| lead_id | Many2one('crm.lead') | |
| triggered_by_user_id | Many2one('res.users') | |
| _sql_constraints | unique external_id, unique htf_ivr_id | |

### htf.dnc
| Field | Type | Notes |
|---|---|---|
| phone | Char(20) | E.164, indexed |
| reason | Char | |
| captured_keyword | Char | what triggered automatic DNC |
| source | Selection [automatic, manual] | |
| added_by_user_id | Many2one('res.users') | |
| added_at | Datetime | |
| reactivated_by_user_id | Many2one('res.users') | nullable |
| reactivated_at | Datetime | nullable |
| state | Selection [active, reactivated] | |
| _sql_constraints | unique active per phone | |

### htf.webhook.event (for idempotency)
| Field | Type | Notes |
|---|---|---|
| event_id | Char | unique key from payload (e.g. messageId, callId, ivr id) |
| route | Char | which webhook route received |
| received_at | Datetime | |
| processed | Boolean | |
| payload_hash | Char(64) | sha256 of body |
| _sql_constraints | unique event_id per route | dedup guard |

### Extensions on existing models

#### res.partner
| Field | Type | Notes |
|---|---|---|
| x_htf_contact_id | Char(uuid) | mirrors htf.contact.link.htf_contact_id for fast filter |
| x_htf_synced_at | Datetime | |
| x_htf_last_inbound_at | Datetime | for 24h-window calc |
| x_htf_24h_window_open | Boolean | computed (last_inbound_at within last 24h) |
| x_htf_opted_out | Boolean | linked to active htf.dnc row |
| x_htf_default_channel_id | Many2one('htf.channel') | optional override |
| x_htf_call_count | Integer | smart-button counter |
| x_htf_message_count | Integer | smart-button counter |

#### res.users
| Field | Type | Notes |
|---|---|---|
| x_htf_user_id | Char(uuid) | from htf.user.link |
| x_htf_user_email | Char | mirror for fast match |
| x_htf_role | Selection [owner, member] | |

---

### crm.team (extension)
| Field | Type | Notes |
|---|---|---|
| x_htf_channel_ids | One2many('htf.channel', 'team_id') | reverse — all channels belonging to this team |
| x_htf_default_outbound_wa_channel_id | Many2one('htf.channel') | computed from `htf.channel.default_for_outbound_wa` per team |
| x_htf_default_outbound_call_channel_id | Many2one('htf.channel') | computed similarly |
| x_htf_routing_strategy | Selection [round_robin, least_busy, lead_owner, manual] | how inbound on team's channel routes to agents (default `lead_owner` then fallback `round_robin`) |

## Module: `numo_crm_htf` (bridge)

### Extensions on existing models (inheritance only)

#### crm.lead (additional)
| Field | Type | Notes |
|---|---|---|
| x_htf_last_call_id | Many2one('htf.call', readonly) | latest call |
| x_htf_last_message_id | Many2one('htf.message', readonly) | latest WA |
| x_htf_last_sentiment | Selection [positive, neutral, negative, mixed, unknown] | denorm |
| x_htf_sentiment_history_json | Text | last 10 sentiment values for trend chart |
| x_htf_total_talk_seconds | Integer | sum of call durations |
| x_htf_call_count | Integer | smart-button |
| x_htf_message_count | Integer | smart-button |
| x_htf_ivr_run_count | Integer | smart-button |
| x_htf_pinned_summary | Text | latest AI summary, denormalized |
| x_htf_appt_confirmed | Boolean | for IVR confirmation flow |
| x_htf_appt_followup | Boolean | for IVR no-answer flow |
| x_htf_lead_source_ctwa | Boolean | click-to-WhatsApp ad attribution |
| x_htf_ctwa_metadata_json | Text | referral payload |

### New models

#### numo_crm_htf.daily_digest_log
| Field | Type | Notes |
|---|---|---|
| user_id | Many2one('res.users') | |
| sent_at | Datetime | |
| missed_calls_count | Integer | |
| unread_messages_count | Integer | |
| silent_positive_leads_count | Integer | |

#### numo_crm_htf.ivr_action_config
Stored as data XML, not user-editable in v1. One row per use case (`appointment-confirm`, `payment-reminder`, etc.)
| Field | Type | Notes |
|---|---|---|
| key | Char | `appointment-confirm` |
| display_name | Char | |
| tts_text | Text | |
| audio_file_url | Char | |
| voice | Selection [male, female] | |
| options_json | Text | digits + descriptions |
| digit_to_action_map_json | Text | `{"1": "confirm_appt", "2": "cancel_appt"}` |
| max_retries | Integer | |
| input_timeout_ms | Integer | |
| digit_timeout_ms | Integer | |

---

## Indexes & Constraints

- `htf.call.htf_call_id` UNIQUE INDEX
- `htf.message.htf_message_id` UNIQUE INDEX (where not null)
- `htf.message.conversation_event_id` INDEX
- `htf.webhook.event.(event_id, route)` UNIQUE INDEX
- `htf.dnc.phone` INDEX (active rows only via partial index)
- `res.partner.x_htf_contact_id` INDEX
- `res.users.x_htf_user_id` INDEX
- `htf.contact.link.partner_id` UNIQUE INDEX (one Hatif contact per partner max)

## Phone Normalization

All numbers stored E.164 (`+9665...`). Use `phonenumbers` lib at the boundary (webhook in / API call out). Reject any non-normalizable input with an error in the source layer.

## Data Lifecycle

- Webhook event records older than 90 days → archive (state=processed, payload_hash kept for audit)
- Call recordings: do NOT mirror to Odoo by default (Hatif holds them). Optional fetch-on-demand cache when user plays.
- DNC: never auto-deleted. `reactivated_*` fields capture lifecycle.
- AI summary, transcription: stored verbatim (search needed for QA later)
