# Signal Bus — Event Registry

A lightweight in-process pub/sub used by the vendor wrapper to notify subscribers (the bridge) when interesting things happen.

Implementation: a simple registry under `htf_call_center.signals`. Subscribers register via `htf_signals.subscribe('signal.name', callback)`. The wrapper fires events synchronously inside the same Odoo transaction (rollback-safe).

---

## Why signals (vs. direct calls)

- Vendor wrapper has zero knowledge of CRM
- Bridge can be uninstalled without breaking wrapper
- Other consumers (e.g. helpdesk integration) can hook the same events
- Tests can register dummy subscribers per case

---

## Signals

### `htf.call.received`
Fired when an answered call has been logged from a webhook.

**Payload:**
```python
{
    'call': htf.call,             # the saved record
    'partner': res.partner | None,
    'is_inbound': bool,
    'recording_url': str | None,
}
```
**Subscribers:** bridge attaches to lead, posts AI summary, updates sentiment trend.

---

### `htf.call.missed`
Fired for status=missed/no_answer/rejected_callee/cancelled.

**Payload:**
```python
{
    'call': htf.call,
    'partner': res.partner | None,
    'caller_number': str,
    'channel': htf.channel,
}
```
**Subscribers:** bridge auto-creates `mail.activity` of type "Phone Call".

---

### `htf.call.failed`
Fired for status=failed.

**Payload:**
```python
{
    'call': htf.call,
    'reason': str,
}
```
**Subscribers:** bridge logs to admin alert channel.

---

### `htf.wa.inbound`
Fired when an inbound WhatsApp message has been logged.

**Payload:**
```python
{
    'message': htf.message,
    'partner': res.partner,
    'channel': htf.channel,
    'is_first_inbound_today': bool,
    'opens_24h_window': bool,
    'is_opt_out_keyword': bool,
}
```
**Subscribers:** bridge attaches to lead; DNC listener auto-blocks if opt_out keyword.

---

### `htf.wa.outbound`
Fired when outbound WA send succeeds.

**Payload:**
```python
{
    'message': htf.message,
    'partner': res.partner,
    'channel': htf.channel,
    'sender_user': res.users,
    'meta_category': str,    # marketing | utility | authentication | service
    'cost_estimate': float,
}
```
**Subscribers:** bridge for cost tracking + chatter post.

---

### `htf.wa.status`
Fired when message status changes (delivered, read, failed).

**Payload:**
```python
{
    'message': htf.message,
    'old_state': str,
    'new_state': str,
    'error_code': int | None,
    'error_reason': str | None,
}
```
**Subscribers:** chatter UI updates the bubble's status icon.

---

### `htf.ivr.result`
Fired when an IVR webhook completes.

**Payload:**
```python
{
    'run': htf.ivr.run,
    'partner': res.partner | None,
    'lead': crm.lead | None,
    'config_key': str,
    'pressed_digit': str | None,
    'result': str,
    'is_terminal': bool,
}
```
**Subscribers:** bridge maps digit → action (confirm/cancel/etc).

---

### `htf.contact.synced`
Fired after contact create/update mirror with Hatif.

**Payload:**
```python
{
    'partner': res.partner,
    'link': htf.contact.link,
    'direction': str,  # 'odoo_to_htf' | 'htf_to_odoo'
}
```
**Subscribers:** bridge can refresh enriched fields, pipeline counters.

---

### `htf.user.mapping.changed`
Fired when an admin saves res.users ↔ Hatif user mapping.

**Payload:**
```python
{
    'user': res.users,
    'old_htf_user_id': str | None,
    'new_htf_user_id': str | None,
}
```
**Subscribers:** bridge can re-attribute historical conversations.

---

### `htf.dnc.added`
Fired when a phone is added to DNC.

**Payload:**
```python
{
    'phone_e164': str,
    'reason': str,
    'source': str,  # automatic | manual
    'partner': res.partner | None,
    'user': res.users | None,
}
```
**Subscribers:** bridge cancels pending IVRs, marks `partner.x_htf_opted_out`.

---

## Subscribing pattern

```python
from htf_call_center.signals import htf_signals

class HtfEventHandler(models.AbstractModel):
    _name = 'numo_crm_htf.event_handler'

    def _register_hook(self):
        htf_signals.subscribe('htf.call.received', self._on_call_received)
        htf_signals.subscribe('htf.call.missed',   self._on_call_missed)
        # ...

    def _on_call_received(self, payload):
        call = payload['call']
        # bridge logic here
```

---

## Firing pattern (vendor wrapper internal)

```python
from htf_call_center.signals import htf_signals

# inside controller after persisting call
htf_signals.fire('htf.call.received', {
    'call': call,
    'partner': call.partner_id,
    'is_inbound': call.direction == 'inbound',
    'recording_url': call.recording_url,
})
```

---

## Synchronous + transactional rules

- All subscribers run in the same transaction as the firing code
- A subscriber that raises rolls the whole webhook back (we want this for invariants)
- Long-running subscribers MUST defer work via `ir.cron` or `bus.bus` — never block the webhook controller
- Order of subscriber execution is registration order (deterministic for tests)

---

## Testing

- Each signal has a fixture that patches the registry to a fresh isolated dict per test
- Bridge tests register dummy subscribers and assert payload shape
- Wrapper tests fire signals against a stub subscriber and assert correct call

---

## Versioning

Signal payloads are PART of the public contract. Adding a key is non-breaking. Removing or renaming = MAJOR bump in vendor module.
