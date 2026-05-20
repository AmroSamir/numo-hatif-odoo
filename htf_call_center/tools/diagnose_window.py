"""Diagnose the WhatsApp 24h-window state for a partner.

Run from the odoo shell — NOT as a standalone script. Usage:

    docker exec -i web-erp-amro-pro odoo shell -d numo --no-http --log-level=warn \\
        -c "exec(open('/mnt/extra-addons/htf_call_center/tools/diagnose_window.py').read())"

Or, simpler, from inside the container shell:

    docker exec -it web-erp-amro-pro odoo shell -d numo --no-http
    >>> exec(open('/mnt/extra-addons/htf_call_center/tools/diagnose_window.py').read())

Set HTF_DIAG_PHONE to scope the search to a specific number; otherwise
the script reports across all partners that have inbound history.
"""

import datetime
import os

PHONE_HINT = os.environ.get('HTF_DIAG_PHONE') or '56 186 8578'


def diagnose(env, phone_hint):
    Partner = env['res.partner'].sudo()
    Msg = env['htf.message'].sudo()

    digits_only = ''.join(ch for ch in phone_hint if ch.isdigit())
    candidates = Partner.search([
        '|', '|', '|',
        ('phone', 'ilike', phone_hint),
        ('phone', 'ilike', digits_only),
        ('phone', 'ilike', f'+{digits_only}'),
        ('mobile', 'ilike', phone_hint),
    ], limit=5)
    if not candidates:
        print(f'NO PARTNER MATCHED phone-hint={phone_hint!r}')
        return

    print(f'now (UTC naive): {datetime.datetime.utcnow()}')
    print(f'matched {len(candidates)} partner(s) for hint={phone_hint!r}:')
    print('-' * 70)
    for p in candidates:
        print(f'partner id={p.id} name={p.name!r}')
        print(f'  phone:                       {p.phone!r}')
        print(f'  mobile:                      {p.mobile!r}')
        print(f'  x_htf_last_inbound_at:       {p.x_htf_last_inbound_at!r}')
        print(f'  x_htf_24h_window_open (cpt): {p.x_htf_24h_window_open}')
        print(f'  x_htf_last_conversation_id:  {p.x_htf_last_conversation_id!r}')
        print(f'  x_htf_opted_out (DNC):       {p.x_htf_opted_out}')
        print(f'  x_htf_discuss_channel_id:    {p.x_htf_discuss_channel_id.id if p.x_htf_discuss_channel_id else None}')
        n_in = Msg.search_count([('partner_id', '=', p.id), ('direction', '=', 'inbound')])
        n_out = Msg.search_count([('partner_id', '=', p.id), ('direction', '=', 'outbound')])
        print(f'  htf.message counts:          inbound={n_in}, outbound={n_out}')
        last_in = Msg.search([
            ('partner_id', '=', p.id), ('direction', '=', 'inbound'),
        ], order='created_at desc', limit=1)
        if last_in:
            body_preview = (last_in.body or '').replace('\n', ' ')[:60]
            print(f'  latest inbound:              id={last_in.id} '
                  f'created_at={last_in.created_at} body={body_preview!r}')
            if p.x_htf_last_inbound_at != last_in.created_at:
                print(f'  ⚠️  MISMATCH: partner.x_htf_last_inbound_at != latest inbound row.')
                print(f'     This is the smoking gun — webhook handler did NOT write')
                print(f'     x_htf_last_inbound_at when this inbound was processed.')
        else:
            print(f'  latest inbound:              <none>')
        if p.x_htf_last_inbound_at:
            age = datetime.datetime.utcnow() - p.x_htf_last_inbound_at
            print(f'  age of last inbound:         {age}')
        print('-' * 70)


# `self` is bound to res.users(uid) inside odoo shell. `env` is set up
# by the shell harness — re-derive defensively.
try:
    _env = self.env  # type: ignore[name-defined]  # noqa: F821
except NameError:  # pragma: no cover — running outside odoo shell
    _env = None

if _env is None:
    print('ERROR: this script must be run inside `odoo shell` — not as a standalone.')
else:
    diagnose(_env, PHONE_HINT)
