"""In-process synchronous signal bus for the HTF wrapper.

Subscribers register at module load time (`_register_hook`). The wrapper fires
events synchronously inside the same Odoo transaction so a subscriber raising
an exception rolls the webhook back. This is intentional — invariants like
"every persisted call also gets a chatter post" depend on it.

Signal names + payload shapes are documented in SIGNAL_BUS.md and are part of
the public contract.
"""

import logging
import threading
from collections import defaultdict
from typing import Callable

_logger = logging.getLogger(__name__)

Subscriber = Callable[[dict], None]


class HtfSignalBus:
    """Module-level singleton registry.

    Order of subscriber execution = registration order (deterministic for tests).
    """

    def __init__(self):
        self._subs: dict[str, list[Subscriber]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, name: str, callback: Subscriber) -> None:
        with self._lock:
            if callback in self._subs[name]:
                return  # idempotent re-subscribe (e.g. registry rebuild)
            self._subs[name].append(callback)

    def unsubscribe(self, name: str, callback: Subscriber) -> None:
        with self._lock:
            if callback in self._subs.get(name, ()):
                self._subs[name].remove(callback)

    def fire(self, name: str, payload: dict) -> None:
        """Call every subscriber for `name` with `payload`.

        Errors propagate to the caller (typically a webhook controller) so the
        Odoo transaction rolls back. This is the desired behavior.
        """
        with self._lock:
            subs = list(self._subs.get(name, ()))  # snapshot, allow re-entry

        for callback in subs:
            callback(payload)

    def subscribers(self, name: str) -> list[Subscriber]:
        """Inspection helper for tests."""
        with self._lock:
            return list(self._subs.get(name, ()))

    def clear(self) -> None:
        """Test-only reset. Production code never calls this."""
        with self._lock:
            self._subs.clear()


# Module-level singleton.
htf_signals = HtfSignalBus()
