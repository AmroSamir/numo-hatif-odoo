/** @odoo-module **/
/**
 * v19.0.1.35.0 — Discuss-first WhatsApp composer.
 *
 * When the agent opens a Hatif-linked channel (those with
 * ``x_htf_partner_id`` pushed to the OWL store by
 * ``discuss.channel._to_store_defaults``), the composer must:
 *
 *   1. Disable the textarea when Meta's 24h window is closed —
 *      ``thread.windowOpen`` (defined in ``thread_model_patch.js``)
 *      is the reactive source of truth. We greyout the input pocket
 *      via a class on the inputContainer (composer_banner.xml +
 *      htf_composer.scss).
 *
 *   2. Show a warning banner above the input pocket explaining why
 *      it's disabled, with a prominent "Send Template" call-to-action
 *      button INSIDE the banner. Clicking the button opens the
 *      existing Send WhatsApp wizard in template mode.
 *
 *   3. Disable the native Send button via ``isSendButtonDisabled``
 *      so even if the textarea workaround fails the send still
 *      can't fire from the UI. The service-layer
 *      ``services/whatsapp.py:_check_window`` is the final gate
 *      and remains untouched.
 *
 * Re-enable path: when the customer replies, the standard discuss
 * bus push appends the new mail.message to ``thread.messages``,
 * ``thread.windowOpen`` recomputes True, OWL re-renders this
 * composer, the banner disappears, the pocket un-greys, and the
 * Send button re-enables. All reactive — no manual refresh.
 *
 * Design note: we tried wiring the "Send Template" via
 * ``registerComposerAction`` first (composer-actions registry) but
 * composer actions in Odoo 19 render as icon-only toolbar buttons —
 * not the prominent labeled call-to-action the UX called for.
 * Moving the button inside the banner gives it the visual weight an
 * agent expects when the window is closed.
 *
 * ── Out-of-scope reminders for future sessions ──────────────────
 *   - Mobile composer behaviour: this patch was tested on desktop
 *     OWL only. The mobile composer in Odoo 19 reuses the same
 *     component with a different layout — likely works as-is but
 *     untested. Follow-up if a user reports mobile breakage.
 *   - Inline template picker: clicking "Send Template" still opens
 *     the existing modal wizard. A future enhancement could render
 *     the approved-template dropdown directly inside the banner.
 *   - Window-closes-at countdown badge ("12h 34m left"): out of
 *     scope. Would require the stored ``x_htf_window_closes_at``
 *     Datetime field discussed but not built.
 */

import { patch } from "@web/core/utils/patch";
import { Composer } from "@mail/core/common/composer";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(Composer.prototype, {
    setup() {
        super.setup();
        // Wire the action service so the in-banner "Send Template"
        // button can do_action() the existing Send WhatsApp wizard
        // with template mode preselected.
        this._htfAction = useService("action");
    },

    /**
     * Hatif-linked thread with closed 24h window? Used by the XML
     * template (composer_banner.xml) to (a) show the banner + button,
     * (b) toggle the pocket-disabled class, and by the patched
     * isSendButtonDisabled below to grey the native Send button.
     *
     * Reactive automatically: reads from props.composer.thread which
     * OWL rebinds on every render, and from thread.windowOpen which
     * recomputes when this.messages updates.
     */
    get htfIsWindowClosed() {
        const thread = this.props?.composer?.thread;
        if (!thread || !thread.x_htf_partner_id) {
            return false;
        }
        return thread.windowOpen === false;
    },

    /** Bilingual banner string — hardcoded so it works pre-translation. */
    get htfBannerLabel() {
        return _t(
            "24-hour reply window is closed. To re-start the conversation, " +
            "send an approved WhatsApp template. Free-form text will be " +
            "enabled when the customer replies."
        );
    },

    /** Label on the prominent in-banner button. */
    get htfSendTemplateLabel() {
        return _t("Send Template");
    },

    /**
     * Disable the native Send button while the window is closed.
     * Belt-and-suspenders with the textarea greying — service-layer
     * _check_window remains the final gate.
     */
    get isSendButtonDisabled() {
        if (this.htfIsWindowClosed) {
            return true;
        }
        return super.isSendButtonDisabled;
    },

    /**
     * Click handler for the in-banner "Send Template" button.
     * Pulls the partner from thread.x_htf_partner_id and launches the
     * existing wizard with default_mode='template'. Wizard handles
     * the actual template send via its existing logic — nothing else
     * changes about how templates work.
     */
    onClickHtfSendTemplate(ev) {
        ev?.preventDefault?.();
        ev?.stopPropagation?.();
        const thread = this.props?.composer?.thread;
        if (!thread?.x_htf_partner_id) {
            return;
        }
        const partnerId =
            typeof thread.x_htf_partner_id === "object"
                ? thread.x_htf_partner_id.id
                : thread.x_htf_partner_id;
        this._htfAction.doAction(
            "htf_call_center.action_htf_send_whatsapp_wizard",
            {
                additionalContext: {
                    default_mode: "template",
                    default_partner_id: partnerId,
                    active_model: "res.partner",
                    active_id: partnerId,
                    active_ids: [partnerId],
                },
            },
        );
    },
});
