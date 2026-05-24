/** @odoo-module **/
/**
 * Client-action handler: ``htf_call_center.open_discuss_chat``.
 *
 * Invoked from ``res.partner.action_htf_open_whatsapp`` and
 * ``crm.lead.action_htf_open_whatsapp`` when the workspace flag
 * ``whatsapp_button_opens_discuss`` is True. Receives
 * ``{params: {channel_id, partner_id}}`` and opens that channel as a
 * Discuss chat-window popup (same surface as clicking a notification
 * in the bell menu).
 *
 * No DOM rendering — registers a "soft" action that exits via
 * actionService's softNavigateBack so the user stays on the current
 * form view. The discuss store handles the popup lifecycle.
 *
 * Why the indirection (server returns a client action vs the JS
 * widget calling .open() directly): keeping the entry point on the
 * server side means every "Send WhatsApp" surface — partner form
 * header, lead form header, htf_phone widget, future kanban
 * quick-actions, automated server actions — funnels through ONE
 * Python method (``action_htf_open_whatsapp``). The Python method is
 * the single seam where we decide "popup vs wizard" and we never have
 * to chase that decision into multiple JS callsites.
 */

import { registry } from "@web/core/registry";

async function openHtfDiscussChat(env, action) {
    const params = action?.params || {};
    const channelId = params.channel_id;
    if (!channelId) {
        console.warn("[htf] open_discuss_chat called with no channel_id");
        return false;
    }
    const store = env.services["mail.store"];
    if (!store) {
        console.warn("[htf] mail.store service unavailable");
        return false;
    }
    // Fetch or hydrate the Thread record for the channel id.
    const thread = await store.Thread.getOrFetch({
        model: "discuss.channel",
        id: channelId,
    });
    if (!thread) {
        console.warn(`[htf] could not fetch discuss.channel id=${channelId}`);
        return false;
    }
    // open() is the same call the notification bell uses (see
    // mail/static/src/core/public_web/messaging_menu.js onClickThread).
    // bypassCompact=true makes the popup show even when the layout
    // wants to collapse it — agents clicking the button always want
    // an explicit popup.
    await thread.open({
        focus: true,
        fromMessagingMenu: false,
        bypassCompact: true,
    });
    // Returning false tells the actionService not to push this action
    // onto the breadcrumb stack — the underlying form view stays put.
    return false;
}

registry.category("actions").add(
    "htf_call_center.open_discuss_chat",
    openHtfDiscussChat,
);
