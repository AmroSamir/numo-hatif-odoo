/** @odoo-module **/
/**
 * HTF phone widget — extends Odoo's FormPhoneField with two buttons:
 *
 *   [📞 Call]   →  tel:<E.164> deep-link (or Hatif app scheme if configured)
 *   [💬 WhatsApp] →  opens the Send WhatsApp wizard with this partner
 *
 * Registered as `htf_phone` in the field registry. Activate with
 * `widget="htf_phone"` on the partner/lead phone field in the view.
 *
 * Falls back gracefully when:
 *   - the value is empty → both buttons hide
 *   - the form record has no partner_id context → WA button hides
 */

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { phoneField, PhoneField } from "@web/views/fields/phone/phone_field";

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
