"""Signal-bus smoke test (P2 T2.6).

Subscribes one listener per WA signal name, asserts payloads arrive
with the documented keys, and prints a green report. Run from
``odoo shell``::

    docker exec -i odoo-app odoo shell -d odoo --no-http <<'PY'
    from odoo.addons.htf_call_center.tools import signal_smoke
    signal_smoke.run(env)
    PY

This is *not* a unit test — it's a hand-driven smoke probe useful when
the bridge (``numo_crm_htf``) registers its real subscribers and you
want to confirm the bus is alive without sending a real webhook.
"""

from __future__ import annotations

import logging

from ..signals import htf_signals

_logger = logging.getLogger(__name__)


SIGNAL_NAMES = (
    'htf.wa.inbound',
    'htf.wa.outbound',
    'htf.wa.status',
    'htf.wa.optout',
)


def run(env, fire_once: bool = True) -> dict:
    """Subscribe a recording listener to each WA signal, optionally fire
    a dummy event of each kind, and return the captured payloads.

    Returns ``{signal_name: [payload, ...]}``. Caller cleans up by
    calling :func:`detach` with the same listener references.
    """
    captured: dict[str, list[dict]] = {n: [] for n in SIGNAL_NAMES}
    listeners: dict[str, callable] = {}

    for name in SIGNAL_NAMES:
        def _make(sig=name):
            def _listener(payload):
                captured[sig].append(payload)
            return _listener
        listener = _make()
        htf_signals.subscribe(name, listener)
        listeners[name] = listener

    if fire_once:
        for name in SIGNAL_NAMES:
            htf_signals.fire(name, {'_smoke': True, 'name': name})

    # Auto-detach so a repeated run() call doesn't pile up listeners.
    for name, listener in listeners.items():
        htf_signals.unsubscribe(name, listener)

    summary = {name: len(payloads) for name, payloads in captured.items()}
    _logger.info("[htf-smoke] signal bus alive: %s", summary)
    return captured


def detach(listeners: dict) -> None:
    """Unsubscribe a previously-installed listener map."""
    for name, listener in listeners.items():
        htf_signals.unsubscribe(name, listener)
