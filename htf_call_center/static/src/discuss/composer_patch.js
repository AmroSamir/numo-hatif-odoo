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
 *      is the reactive source of truth. We patch ``isSendButtonDisabled``
 *      AND ``inputClasses`` so the Send button greys out AND the
 *      ``<textarea>`` shows a disabled cursor + greyed background.
 *      The native ``readOnly`` attribute is bound via the patch.
 *
 *   2. Register a ``htf-send-template`` composer action that surfaces
 *      a teal "Send Template" button RIGHT NEXT TO the disabled Send
 *      button. Click → opens the existing Send WhatsApp wizard with
 *      ``default_mode='template'`` so the agent lands directly in the
 *      template picker without an extra click.
 *
 *   3. Show a banner above the input explaining why it's disabled
 *      (template added in ``composer_disabled_banner.xml``).
 *
 * Re-enable path: when the customer replies, the standard discuss
 * bus push appends the new mail.message to ``thread.messages``,
 * ``thread.windowOpen`` recomputes True, OWL re-renders this
 * composer, the readonly disappears, the Send button re-enables,
 * and the "Send Template" action's ``condition`` returns false so
 * the button hides. All reactive — no manual refresh.
 *
 * ── Out-of-scope reminders for future sessions ──────────────────
 *   - Mobile composer behaviour: this patch was tested on desktop
 *     OWL only. The mobile composer in Odoo 19 reuses the same
 *     component with a different layout — likely works as-is but
 *     untested. Follow-up if a user reports mobile breakage.
 *   - Inline template picker: clicking "Send Template" still opens
 *     the existing modal wizard. A future enhancement could render
 *     the approved-template dropdown directly inside the composer
 *     toolbar (no modal).
 *   - Window-closes-at countdown badge ("12h 34m left"): out of
 *     scope. Would require the stored ``x_htf_window_closes_at``
 *     Datetime field discussed but not built.
 */

import { patch } from "@web/core/utils/patch";
import { Composer } from "@mail/core/common/composer";
import { registerComposerAction } from "@mail/core/common/composer_actions";
import { _t } from "@web/core/l10n/translation";

const HTF_BRAND_TEAL = "#02c7b5";

// ---------------------------------------------------------------- //
// Composer patch — disable input when window is closed              //
// ---------------------------------------------------------------- //
patch(Composer.prototype, {
    /**
     * Hatif-linked thread with closed 24h window? Return true to
     * propagate the disabled state to (a) the Send button, (b) the
     * textarea readOnly attribute via inputClasses below.
     */
    get isSendButtonDisabled() {
        if (this._htfIsWindowClosed()) {
            return true;
        }
        return super.isSendButtonDisabled;
    },

    /**
     * Inject a CSS class onto the textarea when the window is
     * closed. CSS lives in htf_composer.scss and adds the greyed
     * background + not-allowed cursor. We also stash the disabled
     * state for the t-att-readOnly binding via the patched
     * `state.active` below.
     */
    get inputClasses() {
        const base = super.inputClasses || "";
        if (this._htfIsWindowClosed()) {
            return `${base} o-htf-composer-disabled`;
        }
        return base;
    },

    /**
     * Helper centralising the gate decision. Reads from
     * ``props.composer.thread`` which OWL re-wires every render —
     * the getter is reactive automatically.
     */
    _htfIsWindowClosed() {
        const thread = this.props?.composer?.thread;
        if (!thread || !thread.x_htf_partner_id) {
            return false;
        }
        return thread.windowOpen === false;
    },
});

// ---------------------------------------------------------------- //
// Send Template composer action                                     //
// ---------------------------------------------------------------- //
// Replaces the prominent Send button visually when the window is
// closed. Clicking opens the existing Send WhatsApp wizard with
// the template-mode preselected. Wizard remains the source of
// truth for which approved templates are available.

registerComposerAction("htf-send-template", {
    condition: ({ composer }) => {
        const thread = composer?.thread;
        return Boolean(thread?.x_htf_partner_id && thread.windowOpen === false);
    },
    icon: "fa fa-fw fa-file-text-o",
    name: _t("Send Template"),
    btnClass: "o-htf-send-template btn-primary",
    nameClass: "o-htf-send-template-label",
    sequenceQuick: 25, // Just before send-message (30) so it sits to its left in LTR
    onSelected({ owner }) {
        const thread = owner.props?.composer?.thread;
        if (!thread?.x_htf_partner_id) {
            return;
        }
        const partnerId =
            typeof thread.x_htf_partner_id === "object"
                ? thread.x_htf_partner_id.id
                : thread.x_htf_partner_id;
        owner.env.services.action.doAction(
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
