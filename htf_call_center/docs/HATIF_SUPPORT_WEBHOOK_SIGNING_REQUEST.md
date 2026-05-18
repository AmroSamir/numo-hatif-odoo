# Hatif Support — WhatsApp Webhook Signing Inquiry

**Workspace:** `3a20ffce-cbdb-02c0-2594-952ef8288ee8` (شركة نمو / Numo)
**Channels under test:**
- `3a20ffce-cc80-7229-8300-a394d13725a4` (أكاديمية نمو, +966 11 500 1591)
- `3a21006b-0441-6c66-ea75-37f20ea5ec4b` (الدعم الفني, +966 11 500 1592)
**Webhook URL configured:** `https://erp.amro.pro/htf/webhook/whatsapp`
**Date:** 2026-05-19

---

## Summary

Your apidog documentation specifies that WhatsApp webhook payloads
are signed using HMAC-SHA256 with the header `X-Voxa-Signature`. We
implemented signature verification accordingly. However, the live
webhook deliveries from `8.213.48.16` do **not** include any
signature header — neither `X-Voxa-Signature` nor any other variant
we've checked.

We can confirm because:

1. The webhook receiver is in production and accepts real inbound +
   outbound STATUS payloads from Hatif.
2. We added diagnostic logging that captures all signature-candidate
   headers on every signature-rejection event.
3. The captured header set for every Hatif POST is:
   `Host`, `X-Real-Ip`, `X-Forwarded-For`, `X-Forwarded-Proto`,
   `Content-Length`, `Content-Type`. Nothing else.

For comparison, here is the documented contract from your apidog
export (Q-03 in our planning docs):

```
Header: X-Voxa-Signature
Algorithm: HMAC-SHA256
Encoding: lowercase hex
Signed payload: raw JSON request body only (no timestamp prefix)
Per-channel webhookSecret (configured on the Hatif portal)
```

---

## Specific questions

1. **Is webhook signing enabled in production?** The docs say yes; live
   delivery shows no signature header. Which is current?

2. **If signing is currently disabled**, when is it scheduled to be
   turned on? We'd like to flip our verification back to strict before
   onboarding more channels.

3. **If signing IS enabled**, what's the per-channel `webhookSecret`
   for the two channels above? It is not visible anywhere in
   `https://app.hatif.io/en/settings/api-connect`. The UI shows only:
   - API Credentials → Client ID + Client Secret (OAuth, confirmed
     working for outbound)
   - API Documentation → Documentation URL + Password (docs portal)
   - Per-channel Post-call Webhook URL + WhatsApp Webhook URL
   
   We tried using the OAuth Client Secret as the webhook secret. Our
   computed HMAC-SHA256 of the raw body does not match anything Hatif
   could be sending (because no signature header is present at all).

4. **What is the published source IP range for Hatif webhook deliveries?**
   So far we have seen `8.213.48.16` exclusively. We'd like to add an
   IP-allowlist on our side as defence-in-depth while signing is unsorted.

---

## Workaround we have in place

Until signing is confirmed, our webhook receiver has a per-tenant
toggle that accepts unsigned payloads and logs the source IP on every
delivery. This is gated on `htf.config.dev_mode_skip_hmac=True` so it
can be flipped back to strict in one config change once the question
above is resolved.

We treat this as a temporary measure — happy to re-engage strict HMAC
verification the moment Hatif publishes the per-channel secret + the
signature header lands on real webhooks.

---

## What we'd love to receive back

A short reply on (1) signing status, (2) ETA if not on yet,
(3) per-channel secret values OR steps to retrieve them, and (4) the
canonical webhook source IP range.

Thank you — happy to share full diagnostic logs / packet captures if
useful.

— Numo / amr.sam.af@gmail.com
