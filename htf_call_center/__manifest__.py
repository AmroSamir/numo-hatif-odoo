{
    'name': 'HTF Call Center',
    'version': '19.0.1.65.0',
    'category': 'Productivity/Discuss',
    'summary': 'Hatif/Voxa BPaaS integration: telephony + WhatsApp + IVR',
    'description': """
HTF Call Center — Vendor Wrapper
================================

Foundation layer that integrates the Hatif/Voxa BPaaS (telephony + WhatsApp
Business API) into Odoo 19. Owns auth, HTTP client, HMAC webhook verification,
raw data models, and the signal bus that bridge modules subscribe to.

This is the "vendor wrapper" half of a two-module pair. The Numo-CRM-specific
automation lives in `numo_crm_htf` (the bridge), which talks to this module
ONLY through the documented public API and signal bus.

Live calling stays in the Hatif web/mobile app. Odoo is the system of record
for every interaction afterwards.
    """,
    'author': 'Numo Higher',
    'website': 'https://numo.sa',
    'depends': [
        'base',
        'mail',
        'contacts',
        'sales_team',
        'crm',
    ],
    'external_dependencies': {
        'python': [
            'requests',
            'phonenumbers',
        ],
    },
    'data': [
        'security/security_groups.xml',
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/ir_cron.xml',
        'data/htf_discuss_mirror.xml',
        # data/htf_public_user_avatar.xml removed — the <field file=…/>
        # syntax didn't persist the image on Odoo 19 for reasons I
        # didn't fully diagnose. The post_init_hook in __init__.py
        # does the same thing programmatically and is reliable.
        'views/res_config_settings_views.xml',
        'views/htf_webhook_event_views.xml',
        # Wizards (with their act_window actions) must load BEFORE any
        # view that references the wizard action xmlid in
        # <button name="%(action_htf_*_wizard)d" .../>. That includes
        # htf_channel_views.xml (Bind to Teams header button) AND
        # res_partner_views.xml + crm_lead_views.xml (Send WA buttons).
        'views/wizard_views.xml',
        'views/htf_channel_views.xml',
        'views/htf_template_views.xml',
        'views/htf_tag_views.xml',
        'views/htf_user_link_views.xml',
        'views/htf_contact_link_views.xml',
        'views/htf_message_views.xml',
        'views/htf_call_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/crm_team_views.xml',
        'views/crm_lead_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.scss',
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.js',
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.xml',
            # P7 polish — widen the Discuss voice-player wrapper from
            # 80px (Odoo default, too narrow) to 240px so call-recording
            # durations render without truncation.
            'htf_call_center/static/src/discuss/htf_voice_player.scss',
            # P7.8 — Hatif ChatWindow header override: hides native call
            # icons on Hatif-linked channels and registers a teal "Call
            # via Hatif" header action that deep-links into the Hatif
            # portal. Server-gated by the `discuss_ui_override` sub-flag
            # (see `discuss_channel._to_store_defaults`). JS-only — the
            # earlier `<t t-inherit="mail.ChatWindow">` xpath approach
            # was dropped because xpath-into-OWL-asset patches break
            # the bundle when upstream re-renders the template.
            'htf_call_center/static/src/discuss/thread_model_patch.js',
            # v19.0.1.35.0 — Discuss-first WhatsApp UX. Client action
            # that opens the per-partner chat popup, composer patch
            # that disables the textarea outside Meta's 24h window
            # and surfaces a Send Template button, plus brand-teal CSS.
            'htf_call_center/static/src/discuss/open_chat_action.js',
            'htf_call_center/static/src/discuss/composer_patch.js',
            'htf_call_center/static/src/discuss/composer_banner.xml',
            'htf_call_center/static/src/discuss/htf_composer.scss',
        ],
    },
    'installable': True,
    'post_init_hook': 'post_init_hook',
    # `application=True` makes Odoo show this module as a top-level app
    # tile on the Apps page AND surfaces it as a tab in the Settings
    # left rail. Required for our <app name="htf_call_center"> block in
    # res.config.settings to actually render as a clickable tab.
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
