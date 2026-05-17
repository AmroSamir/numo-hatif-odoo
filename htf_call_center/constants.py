"""Public constants for the HTF Call Center wrapper.

These are part of the bridge-visible public API. Renaming or removing any of
them requires a MAJOR version bump per API_CONTRACT.md §Versioning.
"""

TIMEOUT_CONNECT_SECONDS = 5
TIMEOUT_READ_SECONDS = 30
TIMEOUT_SECONDS = TIMEOUT_READ_SECONDS  # back-compat alias

RETRY_BUDGET = 3
RETRY_BACKOFF_SECONDS = (1, 2, 4)

TOKEN_REFRESH_LEEWAY_SECONDS = 60
TOKEN_CRON_REFRESH_THRESHOLD_SECONDS = 300  # cron refreshes if < 5 min to expiry

# Webhook signing — confirmed via Hatif apidog export L5088 (Q-03 ANSWERED).
# Hatif white-labels Voxa, so the actual header carries the Voxa brand.
WEBHOOK_SIGNATURE_HEADER = 'X-Voxa-Signature'
WEBHOOK_HASH_ALGO = 'sha256'
WEBHOOK_SIGNED_PAYLOAD = 'raw_body'  # raw JSON body only, no timestamp prefix
WEBHOOK_RESPONSE_DEADLINE_SECONDS = 5

# NOTE: REPLAY_WINDOW_SECONDS intentionally NOT defined. Hatif/Voxa does not
# send a timestamp header, so replay protection relies on event-id idempotency
# (htf.webhook.event UNIQUE constraint) instead of timestamp windows.

META_24H_WINDOW_HOURS = 24

DNC_KEYWORDS_DEFAULT = ('STOP', 'UNSUBSCRIBE', 'إلغاء', 'إلغاء الاشتراك', 'الغاء')

SUPPORTED_LANGUAGES = ('ar', 'en')

# Service registry keys exposed via env['htf.config'].get_service(name).
# Each phase adds its own key. P1 adds channels/tags/workspace/contacts.
SERVICE_AUTH = 'auth'
SERVICE_HTTP = 'http'
SERVICE_CHANNELS = 'channels'
SERVICE_TAGS = 'tags'
SERVICE_WORKSPACE = 'workspace'
SERVICE_CONTACTS = 'contacts'
SERVICE_CONTACT_PROPERTIES = 'contact_properties'

CONFIG_PARAM_PREFIX = 'htf_call_center.'
USER_AGENT = 'HtfCallCenter/19.0 (Odoo)'
