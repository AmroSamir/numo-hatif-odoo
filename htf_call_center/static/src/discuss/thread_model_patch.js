/** @odoo-module **/
/**
 * P7.8 — Hatif overrides on the OWL Thread + ChatWindow header actions.
 *
 * For Hatif-linked channels (those with x_htf_partner_id pushed to the
 * OWL store by `discuss.channel._to_store_defaults`), we:
 *
 *   1. Force ``allowCalls`` to return false. Every native voice / video
 *      / call-settings thread action registered by Odoo's mail module
 *      gates on ``thread.allowCalls``, so flipping this getter makes
 *      them auto-hide. Internal colleague-to-colleague chats are
 *      untouched (no ``x_htf_partner_id``, super getter runs unchanged).
 *
 *   2. Register a "Call via Hatif" header action via the supported
 *      ``registerThreadAction`` registry. It only appears when
 *      ``hatifCallHref`` is truthy. Click opens app.hatif.io/ar/inbox
 *      in a new tab, with the ``conversationId`` deep-link when known.
 *
 * Server-side gate: the OWL store only receives ``x_htf_partner_id`` +
 * ``x_htf_last_conversation_id`` when the ``discuss_ui_override``
 * sub-flag is ON (see ``discuss_channel._to_store_defaults``). With
 * the flag off the patch sees ``undefined``, super.allowCalls runs,
 * the registered action's ``condition`` returns false, and the native
 * Discuss UI is fully restored without restarting Odoo or touching code.
 *
 * Approach choice: this used to be ``<t t-inherit="mail.ChatWindow">``
 * with an xpath inject — that pattern is fragile against upstream
 * refactors and broke the asset bundle in an earlier attempt. The
 * ``registerThreadAction`` registry is the documented extension point
 * for adding ChatWindow header buttons and survives upstream changes.
 */

import { patch } from "@web/core/utils/patch";
import { Thread } from "@mail/core/common/thread_model";
import { registerThreadAction } from "@mail/core/common/thread_actions";
import { _t } from "@web/core/l10n/translation";

const HATIF_PORTAL_BASE = "https://app.hatif.io/ar/inbox";
const HATIF_BRAND_TEAL = "#02c7b5";

patch(Thread.prototype, {
    get allowCalls() {
        if (this.x_htf_partner_id) {
            return false;
        }
        return super.allowCalls;
    },

    /**
     * v19.0.1.35.0 — reactive 24h-window state for the composer patch.
     *
     * Returns true when this thread is either NOT a Hatif-linked
     * channel (so non-Hatif threads behave normally) OR when there
     * is a customer-authored inbound message in the loaded message
     * list whose creation date is within the last 24 hours.
     *
     * Computed CLIENT-side from this.messages so it reactively
     * re-evaluates the moment a new inbound mail.message arrives via
     * the standard discuss bus push — no custom server-side bus
     * notification needed. When a customer replies, OWL appends the
     * message to thread.messages, this getter re-runs, the composer
     * patch sees windowOpen flip to true, and the textarea re-enables
     * within ~1-2 seconds of the webhook hit.
     */
    get windowOpen() {
        if (!this.x_htf_partner_id) {
            return true;
        }
        const partnerId =
            typeof this.x_htf_partner_id === "object"
                ? this.x_htf_partner_id.id
                : this.x_htf_partner_id;
        const cutoff = Date.now() - 24 * 60 * 60 * 1000;
        const messages = this.messages || [];
        for (let i = messages.length - 1; i >= 0; i--) {
            const m = messages[i];
            const authorId =
                m?.author?.id ?? (typeof m?.author === "number" ? m.author : null);
            if (!authorId || authorId !== partnerId) {
                continue;
            }
            const dateObj = m.date instanceof Date ? m.date : new Date(m.date);
            if (!isNaN(dateObj.getTime()) && dateObj.getTime() >= cutoff) {
                return true;
            }
            return false;
        }
        return false;
    },

    /**
     * Deep-link URL for the "Call via Hatif" header button, or
     * ``false`` when the thread is not a Hatif-linked channel.
     *
     * Stitches ``channelId`` + ``conversationId`` into the URL when
     * both are pushed to the OWL store by
     * ``discuss.channel._to_store_defaults``. Matches the canonical
     * Hatif inbox URL shape:
     * ``?channelId=<uuid>&conversationId=<uuid>``. Each param is
     * optional — emitted only when known. Falls back to inbox root
     * when neither is known yet (first activity on a brand-new
     * channel before the first webhook lands).
     */
    get hatifCallHref() {
        if (!this.x_htf_partner_id) {
            return false;
        }
        const params = new URLSearchParams();
        if (this.x_htf_last_channel_uuid) {
            params.set("channelId", this.x_htf_last_channel_uuid);
        }
        if (this.x_htf_last_conversation_id) {
            params.set("conversationId", this.x_htf_last_conversation_id);
        }
        const qs = params.toString();
        return qs ? `${HATIF_PORTAL_BASE}?${qs}` : HATIF_PORTAL_BASE;
    },
});

registerThreadAction("hatif-call", {
    condition: ({ thread }) => Boolean(thread?.hatifCallHref),
    icon: "fa fa-fw fa-phone",
    name: _t("Call via Hatif"),
    open: ({ thread }) => {
        const href = thread.hatifCallHref;
        if (href) {
            window.open(href, "_blank", "noopener,noreferrer");
        }
    },
    // Sit where the native ``call`` action used to render so the header
    // spacing/order stays familiar after the swap.
    sequence: 10,
    sequenceQuick: 30,
    // ``btnClass`` is rendered as a class on the <button> element by
    // mail.Action.main; ``color`` cascades down to the <i> icon and
    // the <span class="o-mail-ActionList-actionLabel"> label so both
    // pick up the Hatif teal. ``btnAttrs`` is defined by the Action
    // class but NOT consumed by the upstream button template in 19.0,
    // so inline style on btnAttrs doesn't render — we have to apply
    // the colour via a CSS class.
    btnClass: "o-htf-hatif-call",
    nameClass: "o-htf-hatif-call-label",
});
