{
    'name': 'HTF Call Center',
    'version': '19.0.1.0.0',
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
        'views/res_config_settings_views.xml',
        'views/htf_webhook_event_views.xml',
        'views/htf_channel_views.xml',
        'views/htf_tag_views.xml',
        'views/htf_user_link_views.xml',
        'views/htf_contact_link_views.xml',
        'views/htf_message_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/crm_team_views.xml',
        'views/wizard_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.scss',
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.js',
            'htf_call_center/static/src/views/fields/phone/htf_phone_field.xml',
        ],
    },
    'installable': True,
    # `application=True` makes Odoo show this module as a top-level app
    # tile on the Apps page AND surfaces it as a tab in the Settings
    # left rail. Required for our <app name="htf_call_center"> block in
    # res.config.settings to actually render as a clickable tab.
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
