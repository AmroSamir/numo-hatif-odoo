# Public API Contract — htf_call_center → Bridge

This is the surface the bridge module (and any future consumer) is allowed to call. **Anything not listed here is internal — touching it breaks the contract.**

---

## Service classes

All services are accessed via `env['htf.config'].get_service('<name>')`.

### `auth`
```python
service = env['htf.config'].get_service('auth')

service.get_token() -> str               # cached, refreshes if needed
service.refresh_token() -> str           # forces refresh
service.invalidate_token() -> None       # on 401
```

### `whatsapp`
```python
service = env['htf.config'].get_service('whatsapp')

service.send_text(
    channel_id: str,           # htf channel UUID
    to_number: str,            # E.164
    text: str,
    *,
    partner=None,              # optional res.partner record
    lead=None,                 # optional crm.lead record
    sender_user=None,          # optional res.users record (default = env.user)
) -> 'htf.message'

service.send_template(
    channel_id: str,
    to_number: str,
    template_name: str,
    language: str,             # 'ar' | 'en'
    parameters: list,          # see _build_parameters helper
    *,
    partner=None,
    lead=None,
    sender_user=None,
) -> 'htf.message'

service.build_body_parameter(values: list[str]) -> dict
service.build_header_image(url: str) -> dict
service.build_header_video(url: str) -> dict
service.build_header_document(url: str, filename: str) -> dict
service.build_header_text(text: str) -> dict
service.build_url_button(index: int, dynamic_part: str) -> dict
service.build_quick_reply_button(index: int, payload: str) -> dict
```

### `calls`
```python
service = env['htf.config'].get_service('calls')

# No outbound API — Hatif app handles live calls.
# Read-only helpers:
service.lookup_partner(phone_e164: str) -> 'res.partner | None'
service.normalize_phone(raw: str) -> str | None
```

### `ivr`
```python
service = env['htf.config'].get_service('ivr')

service.trigger(
    channel_id: str,
    destination_number: str,
    *,
    config_key: str = None,        # uses ivr_action_config from bridge
    tts_text: str = None,
    audio_file_url: str = None,
    voice: str = 'female',
    options: list[dict] = None,    # [{'digit': '1', 'description': 'Confirm'}, ...]
    welcome_url: str = None,
    success_url: str = None,
    failed_url: str = None,
    max_retries: int = 3,
    input_timeout_ms: int = 6000,
    digit_timeout_ms: int = 3000,
    external_id: str = None,       # idempotency
    partner=None,
    lead=None,
    triggered_by_user=None,
) -> 'htf.ivr.run'
```

### `contacts`
```python
service = env['htf.config'].get_service('contacts')

service.upsert_from_partner(partner: 'res.partner') -> 'htf.contact.link'
service.sync_from_htf(htf_contact_id: str) -> 'htf.contact.link'
service.delete(partner: 'res.partner') -> None
service.search_by_property(
    property_definition_id: str,
    operator: int,    # 1 = equals, others TBD from API
    value: str,
) -> list['res.partner']
service.set_property(partner, property_id: str, value) -> None
service.unset_property(partner, property_id: str) -> None
service.import_vcards(vcards: list[str]) -> dict  # {'created': N, 'updated': N, 'errors': [...]}
service.history(partner) -> list[dict]
```

### `conversations`
```python
service = env['htf.config'].get_service('conversations')

service.get_or_create(
    channel_id: str,
    phone_number: str,
    contact_name: str = None,
    assignee_user=None,
    assignee_ai_agent_id: str = None,
) -> 'htf.conversation'

service.assign(conversation, user=None, ai_agent_id=None) -> None

service.list_for_channel(
    channel_id: str,
    *,
    status: str = None,
    assignee_user_ids: list = None,
    contact_ids: list = None,
    tag_ids: list = None,
    name: str = None,
    phone_number: str = None,
    from_date: datetime = None,
    to_date: datetime = None,
    is_lost: bool = None,
    sorting: str = 'LastActivityAt DESC',
    skip: int = 0,
    max: int = 50,
) -> dict  # {total_count: int, items: list[htf.conversation]}

service.get_timeline(
    conversation,
    *,
    sorting: str = 'CreationTime DESC',
    skip: int = 0,
    max: int = 50,
) -> dict
```

### `tags`
```python
service = env['htf.config'].get_service('tags')

service.create(name: str, *, icon: str = None, description: str = None, is_pinned: bool = False) -> 'htf.tag'
service.list() -> 'htf.tag' (recordset)
service.update(tag, **kwargs) -> 'htf.tag'
service.delete(tag) -> None
service.sync_from_htf() -> int  # returns count synced
```

### `workspace`
```python
service = env['htf.config'].get_service('workspace')

service.list_users() -> list[dict]
service.sync_users() -> 'htf.user.link' recordset
service.match_by_email() -> list[tuple[res.users, htf.user.link]]
```

### `audio`
```python
service = env['htf.config'].get_service('audio')

service.upload(file_bytes: bytes, mime_type: str = 'audio/mpeg') -> str  # returns hosted URL
```

### `channels`
```python
service = env['htf.config'].get_service('channels')

service.sync_from_htf() -> 'htf.channel' recordset  # idempotent
service.list_active(*, channel_type: str = None) -> 'htf.channel' recordset
service.default_for_outbound_wa() -> 'htf.channel'
service.default_for_outbound_call() -> 'htf.channel'
```

### `dnc`
```python
service = env['htf.config'].get_service('dnc')

service.is_blocked(phone_e164: str) -> bool
service.block(phone_e164: str, *, reason=None, captured_keyword=None, source='manual', user=None) -> 'htf.dnc'
service.unblock(phone_e164: str, user=None) -> None
service.opt_out_keywords() -> list[str]  # configurable via htf.config
```

---

## Error model

All service methods raise these exceptions on failure (no silent failures):

| Exception | Meaning |
|---|---|
| `htf_call_center.exceptions.HtfApiError` | base class, includes status, body, request id |
| `HtfAuthenticationError` | 401, refresh failed |
| `HtfAuthorizationError` | 403 |
| `HtfNotFoundError` | 404 |
| `HtfRateLimitError` | 429, includes retry_after |
| `HtfServerError` | 5xx |
| `HtfValidationError` | 4xx other |
| `HtfDncBlockedError` | local pre-check failure |
| `HtfWindowExpiredError` | 24h Meta-window blocks free text send |
| `HtfNotMappedError` | res.users has no x_htf_user_id |
| `HtfChannelNotFoundError` | channel not active |

All errors include enough context to log + surface to user.

---

## Constants

```python
# htf_call_center.constants
TIMEOUT_SECONDS = 30
RETRY_BUDGET = 3
RETRY_BACKOFF_SECONDS = (1, 2, 4)
TOKEN_REFRESH_LEEWAY_SECONDS = 60
# REPLAY_WINDOW_SECONDS removed — Hatif/Voxa does NOT send a timestamp header.
# Replay protection = event-id idempotency only (htf.webhook.event UNIQUE constraint).
WEBHOOK_SIGNATURE_HEADER = 'X-Voxa-Signature'  # confirmed apidog L5088, NOT X-Htf-Signature
WEBHOOK_HASH_ALGO = 'sha256'                   # HMAC-SHA256 lowercase hex
WEBHOOK_SIGNED_PAYLOAD = 'raw_body'             # raw JSON body only, no timestamp prefix
WEBHOOK_RESPONSE_DEADLINE_SECONDS = 5          # respond 200 fast, push slow work async
META_24H_WINDOW_HOURS = 24
DNC_KEYWORDS_DEFAULT = ['STOP', 'إلغاء', 'إلغاء الاشتراك', 'الغاء']
SUPPORTED_LANGUAGES = ('ar', 'en')
```

---

## What the bridge MUST NOT do

- Import any module under `htf_call_center.services.*` directly
- Call any method starting with `_` on htf models
- Read `client_secret` or `webhook_secret_*` directly from `htf.config`
- Hit Hatif HTTP endpoints directly (always go through services)
- Bypass DNC check in send paths
- Manipulate `htf.webhook.event` rows (idempotency belongs to the wrapper)

A pylint custom rule enforces the `from htf_call_center.services.*` import ban.

---

## What the bridge CAN do

- Subscribe to signals (see SIGNAL_BUS.md)
- Call `env['htf.config'].get_service(...)` for everything
- Inherit `htf.*` models to add fields ONLY if necessary, prefer linking via `Many2one`
- Read `htf.*` model recordsets via standard Odoo ORM
- Override `_post_to_chatter()` hooks via documented inheritance points

---

## Versioning

- Public API contract follows **semver-like** in module version: 19.0.MAJOR.MINOR.PATCH
- Breaking change → MAJOR bump, bridge `__manifest__.py` enforces depends with `>=` constraint
- Deprecation policy: 1 minor version with deprecation warning before removal
