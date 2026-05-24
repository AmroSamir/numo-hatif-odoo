/** @odoo-module **/
/**
 * HTF phone widget — extends Odoo's FormPhoneField with two buttons:
 *
 *   [📞 Call via Hatif] →  opens app.hatif.io/ar/inbox in a new tab
 *                          (with conversationId deep-link when known)
 *   [💬 WhatsApp]       →  opens the Send WhatsApp wizard with this partner
 *
 * Registered as `htf_phone` in the field registry. Activate with
 * `widget="htf_phone"` on the partner/lead phone field in the view.
 *
 * Why Hatif portal and not `tel:`:
 *   - On a desktop browser `tel:<num>` hands off to the OS protocol
 *     handler (Facetime / Skype / nothing), bypassing Hatif entirely —
 *     so the call is never logged + recorded on the Hatif side.
 *   - The Hatif portal has the softphone dialer + conversation history,
 *     which is what an agent actually needs to make the call.
 *
 * Conversation ID resolution:
 *   - res.partner → `record.data.x_htf_last_conversation_id` (the partner
 *     model stores this directly, mirrored from the most recent webhook).
 *     View must declare the field so it's loaded into record.data.
 *   - crm.lead → no `x_htf_last_conversation_id` on the lead itself, so
 *     we fall back to the inbox base URL. The agent finds the customer
 *     in Hatif by phone search.
 *
 * Falls back gracefully when:
 *   - the value is empty → both buttons hide
 *   - the form record has no partner_id context → WA button hides
 */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { phoneField, PhoneField } from "@web/views/fields/phone/phone_field";

const HATIF_PORTAL_BASE = "https://app.hatif.io/ar/inbox";

export class HtfPhoneField extends PhoneField {
    static template = "htf_call_center.HtfPhoneField";
    static props = {
        ...PhoneField.props,
    };

    setup() {
        super.setup();
        this.action = useService("action");
    }

    /**
     * Resolve the res.partner id to pass to the Send WhatsApp wizard.
     *
     * - If the current record is `res.partner` → use its id
     * - If the current record is `crm.lead` → use partner_id if set
     * - Otherwise → no WA button (returns false)
     */
    get partnerId() {
        const record = this.props.record;
        if (!record) {
            return false;
        }
        const model = record.resModel;
        if (model === "res.partner") {
            return record.resId || false;
        }
        if (model === "crm.lead") {
            const partner = record.data.partner_id;
            // Many2one comes as [id, name] or null
            if (Array.isArray(partner)) {
                return partner[0] || false;
            }
            return (partner && partner.id) || false;
        }
        return false;
    }

    get hasPhoneValue() {
        return !!(this.props.record && this.props.record.data[this.props.name]);
    }

    /**
     * Hatif portal deep-link for the "Call via Hatif" button.
     *
     * Hatif's portal accepts three query params and the right answer
     * is to send all three when we have them — that's the exact URL
     * shape the Hatif inbox emits when an agent opens a conversation
     * manually (observed example:
     * ``?phone=%2B966561868578&channelId=<uuid>&conversationId=<uuid>``).
     *
     * Resolution:
     *   - ``phone``           ← value of the current phone field, lightly
     *                            normalised. Drops if empty.
     *   - ``channelId``       ← ``x_htf_last_channel_uuid`` (raw Hatif
     *                            workspace channel UUID, mirrored by the
     *                            webhook ``_stamp_conversation_metadata``).
     *                            Drops if empty.
     *   - ``conversationId``  ← ``x_htf_last_conversation_id``. Drops if
     *                            empty.
     *
     * Each param is optional and emitted only when known. With zero
     * params, falls back to the inbox root.
     */
    get hatifCallHref() {
        const data = this.props.record?.data || {};
        const params = new URLSearchParams();
        const phone = this._normalizePhoneForUrl(data[this.props.name]);
        if (phone) {
            params.set("phone", phone);
        }
        if (data.x_htf_last_channel_uuid) {
            params.set("channelId", data.x_htf_last_channel_uuid);
        }
        if (data.x_htf_last_conversation_id) {
            params.set("conversationId", data.x_htf_last_conversation_id);
        }
        const qs = params.toString();
        return qs ? `${HATIF_PORTAL_BASE}?${qs}` : HATIF_PORTAL_BASE;
    }

    /**
     * Light client-side normaliser for the ``?phone=`` query param.
     *
     * - Strips whitespace, dashes, parentheses, dots — common UI noise.
     * - Preserves a leading ``+`` if the raw value already had one,
     *   so E.164 values like ``+966 57 983 5885`` survive as
     *   ``+966579835885``.
     * - Does NOT try to add country codes — the server-side
     *   ``utils.phone.normalize_e164`` is the canonical normaliser and
     *   we don't want to second-guess it from JS. Falls back to the
     *   trimmed digits-only string for non-international input.
     */
    _normalizePhoneForUrl(raw) {
        if (!raw) {
            return "";
        }
        const trimmed = String(raw).trim();
        if (!trimmed) {
            return "";
        }
        const startsWithPlus = trimmed.startsWith("+");
        const digits = trimmed.replace(/\D+/g, "");
        if (!digits) {
            return "";
        }
        return startsWithPlus ? `+${digits}` : digits;
    }

    async onWhatsAppClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const partnerId = this.partnerId;
        if (!partnerId) {
            return;
        }
        await this.action.doAction(
            "htf_call_center.action_htf_send_whatsapp_wizard",
            {
                additionalContext: {
                    active_model: "res.partner",
                    active_id: partnerId,
                    active_ids: [partnerId],
                    // Pre-fill phone from the current field so the wizard
                    // doesn't need to re-resolve from partner.phone.
                    default_to_number: this.props.record.data[this.props.name] || "",
                },
            }
        );
    }
}

export const htfPhoneField = {
    ...phoneField,
    component: HtfPhoneField,
    displayName: _t("Phone (HTF — Call + WhatsApp)"),
};

registry.category("fields").add("htf_phone", htfPhoneField);
