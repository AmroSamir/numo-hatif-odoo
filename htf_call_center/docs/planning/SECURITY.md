# Security

Threat model + controls. Audit before each prod release.

---

## Secrets management

| Secret | Storage | Access |
|---|---|---|
| `client_id` | `htf.config.client_id` (encrypted via field group) | Admin group only |
| `client_secret` | `htf.config.client_secret` (write-only after first save) | Admin group only |
| `webhook_secret_current` / `previous` | `htf.config` | Admin group only |
| `token_cache` | `htf.config.token_cache` | wrapper internal only |

**Rules:**
- Secrets never exposed in chatter, log lines, error messages, or HTTP headers in error states
- Custom log filter strips `Authorization: Bearer ...` headers
- Form views use `password='True'` widget; backend marks field with `groups='htf_call_center.group_admin'`
- Settings export/backup excludes secret fields
- Webhook secret rotation supports a 7-day overlap window (`current` + `previous` both accepted)

---

## Webhook authentication

Every webhook route requires:
1. **Signature header** (`X-Htf-Signature` — exact name confirmed with Hatif team)
2. **Timestamp header** (`X-Htf-Timestamp`) — within ±5 min of server time
3. **Body**

Verification:
```python
expected = hmac.new(secret_bytes, f"{timestamp}.{raw_body}".encode(), hashlib.sha256).hexdigest()
ok = hmac.compare_digest(expected, signature_header)
```

- Reject 401 if signature missing, malformed, or mismatch
- Reject 401 if timestamp outside window (replay protection)
- Try both `current` and `previous` secret to support rotation
- Log failed verifications with source IP at WARNING level
- After N failures from an IP in 5 min → admin alert via mail template
- Endpoint URL itself can be considered a weak secret (path includes random suffix), but signature is the real gate

---

## Idempotency

- `htf.webhook.event` table stores `(event_id, route)` UNIQUE
- On duplicate → return 200 immediately, no DB writes, no signal fire
- Event IDs:
  - Call: `webhook.id` (vendor-generated)
  - WA: `messageId`
  - IVR: `id` from Hatif IVR run

This protects against:
- Hatif retrying a webhook after a network blip
- Replay attacks (combined with timestamp window)
- Re-processing during DB rollback + redelivery

---

## Outbound HTTPS

- All API calls to `api.voxa.sa` use HTTPS only (no http fallback)
- TLS verification ON (no `verify=False`)
- Connection timeout 5s, read timeout 30s
- Custom User-Agent: `HtfCallCenter/19.0 (Odoo)`
- Retry policy: 3 attempts, exponential backoff (1s, 2s, 4s) on 5xx + connection errors
- Never retry on 4xx (validation errors are deterministic)

---

## Access groups

```
htf_call_center.group_user
  → can: read own calls, send WA from own leads, view conversations assigned to self
  → cannot: see other agents' interactions, edit DNC, change settings

htf_call_center.group_admin
  → inherits group_user
  → can: edit settings, manage channels/tags/templates, run user mapping wizard, view all DNC
```

The bridge module does NOT add new groups — it relies on existing CRM groups + the wrapper's two.

---

## Record rules

```python
# htf.call — agent sees only own
('user', "[('handler_user_id', '=', user.id), ('handler_user_id', 'in', user.team_member_ids.ids)]")

# htf.message — same rule
('user', "['|', ('sender_user_id', '=', user.id), ('partner_id.user_id', '=', user.id)]")

# htf.conversation — assignee or partner owner
('user', "['|', ('assignee_user_id', '=', user.id), ('partner_id.user_id', '=', user.id)]")
```

Admin sees all (no rule).

---

## DNC enforcement

- Pre-flight check on every outbound send (text and template)
- Cannot be bypassed by user — enforced in service layer
- Manual unblock requires admin role + reason
- Audit log on DNC add/remove (`mail.activity` chatter on partner, plus dedicated audit table)

---

## 24h Meta-window enforcement

- Free-form text outbound only allowed if `partner.x_htf_last_inbound_at` < 24h
- UI shows window timer chip, disabled-state composer when expired
- Service layer also enforces — UI can't bypass via XSS or POST tampering
- Templates always allowed (Meta rules)

---

## PII handling

- Transcripts stored verbatim — privacy notice required for KSA PDPL compliance
- Optional regex-based redaction (Saudi NID `\d{10}`, IBAN `SA\d{22}`, credit card)
- Recordings NOT mirrored by default (Hatif retains)
- Export/delete on customer request: dedicated wizard handles `partner.x_htf_*` purge
- Admin audit log on every export/delete

---

## CSRF

Webhook routes are `csrf=False` (HMAC replaces CSRF for unauthenticated POST).
Internal Odoo wizards/buttons use Odoo's standard CSRF protection (no override).

---

## Rate limiting

- Outbound API client respects 429 → backs off per `Retry-After`
- Optional local rate limiter on `whatsapp.send_*` for bulk sends (configurable msgs/sec, default 5)
- DoS protection on webhooks: rely on Odoo + Nginx layer (already configured)

---

## Logging

- INFO: API call summary (method, path, status, duration) — NEVER body
- DEBUG (only when `htf.config.debug_log_enabled`): full request/response, secrets stripped
- WARNING: HMAC fail, retry exhaustion, refresh fail
- ERROR: unexpected exceptions
- All log lines tagged `[htf]` for grep
- Logs flow into Odoo's `ir.logging` (already standard)

---

## Test coverage gates

- 100% coverage on auth + HMAC verify modules
- 90%+ on services
- 80%+ overall

CI fails the build if coverage drops.

---

## Pre-prod checklist

Before flipping prod traffic:
- [ ] Webhook URLs registered with Hatif team
- [ ] HMAC secret seeded in `htf.config`
- [ ] Webhook IP allowlist confirmed (if Hatif provides)
- [ ] Test connection succeeds from Settings page
- [ ] Test webhook payload (Hatif team replays a real one) succeeds
- [ ] DNC keywords list confirmed (Arabic + English)
- [ ] Admin alert email recipient set
- [ ] All default channels mapped to teams
- [ ] User mapping wizard run, no unmapped Hatif users in active workspace
- [ ] Backup taken before module install
