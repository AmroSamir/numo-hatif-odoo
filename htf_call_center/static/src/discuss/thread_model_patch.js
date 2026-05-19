/** @odoo-module **/
/**
 * P7.5 — Hatif overrides on the OWL Thread model.
 *
 * For Hatif-linked channels (those with x_htf_partner_id populated by
 * the server-side mirror), we:
 *
 *   1. Force allowCalls to return false — this hides every native
 *      voice-call button in the ChatWindow header because the
 *      built-in thread_actions registrations gate on
 *      `thread.allowCalls`. Internal colleague-to-colleague chats are
 *      untouched (they have no x_htf_partner_id).
 *
 *   2. Expose `hatifCallHref` — the deep-link target for the custom
 *      "Call via Hatif" button rendered by chat_window.xml. Uses the
 *      stored conversationId when known, falls back to the inbox root.
 *
 * Activation is gated on the server side by the `discuss_ui_override`
 * sub-flag: when the flag is off, `_to_store_defaults` doesn't push
 * x_htf_partner_id to the frontend, so the patch's checks see
 * `undefined` and fall through to the default behaviour.
 */

import { patch } from "@web/core/utils/patch";
import { Thread } from "@mail/core/common/thread_model";

const HATIF_PORTAL_BASE = "https://app.hatif.io/ar/inbox";

patch(Thread.prototype, {
    get allowCalls() {
        if (this.x_htf_partner_id) {
            return false;
        }
        return super.allowCalls;
    },

    /**
     * Returns the deep-link URL for the "Call via Hatif" button or
     * `false` when the thread is not a Hatif-linked channel.
     */
    get hatifCallHref() {
        if (!this.x_htf_partner_id) {
            return false;
        }
        const convoId = this.x_htf_last_conversation_id;
        if (convoId) {
            return `${HATIF_PORTAL_BASE}?conversationId=${encodeURIComponent(convoId)}`;
        }
        return HATIF_PORTAL_BASE;
    },
});
