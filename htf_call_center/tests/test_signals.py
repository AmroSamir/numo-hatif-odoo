"""Signal bus — registration order, fire propagation, unsubscribe, errors."""

from .common import HtfTransactionCase
from ..signals import HtfSignalBus, htf_signals


class TestSignalBus(HtfTransactionCase):

    def test_subscribe_and_fire_calls_callback(self):
        seen = []
        htf_signals.subscribe('test.signal', lambda payload: seen.append(payload))
        htf_signals.fire('test.signal', {'x': 1})
        self.assertEqual(seen, [{'x': 1}])

    def test_registration_order_preserved(self):
        order = []
        htf_signals.subscribe('test.order', lambda p: order.append('first'))
        htf_signals.subscribe('test.order', lambda p: order.append('second'))
        htf_signals.subscribe('test.order', lambda p: order.append('third'))
        htf_signals.fire('test.order', {})
        self.assertEqual(order, ['first', 'second', 'third'])

    def test_unsubscribe_removes_callback(self):
        seen = []

        def handler(payload):
            seen.append(payload)

        htf_signals.subscribe('test.unsub', handler)
        htf_signals.unsubscribe('test.unsub', handler)
        htf_signals.fire('test.unsub', {'x': 1})
        self.assertEqual(seen, [])

    def test_unsubscribe_unknown_handler_noop(self):
        # Should not raise.
        htf_signals.unsubscribe('never.registered', lambda p: None)

    def test_subscriber_exception_propagates(self):
        # The webhook controller relies on this — exception unwinds the
        # transaction.
        def boom(payload):
            raise RuntimeError('subscriber blew up')

        htf_signals.subscribe('test.boom', boom)
        with self.assertRaises(RuntimeError):
            htf_signals.fire('test.boom', {})

    def test_idempotent_subscribe_does_not_duplicate(self):
        seen = []

        def handler(payload):
            seen.append(1)

        htf_signals.subscribe('test.idemp', handler)
        htf_signals.subscribe('test.idemp', handler)
        htf_signals.fire('test.idemp', {})
        self.assertEqual(seen, [1])

    def test_fresh_bus_independent_of_module_singleton(self):
        bus = HtfSignalBus()
        seen = []
        bus.subscribe('local', lambda p: seen.append(p))
        bus.fire('local', {'k': 'v'})
        self.assertEqual(seen, [{'k': 'v'}])
        # Module singleton untouched
        self.assertEqual(htf_signals.subscribers('local'), [])

    def test_subscribers_inspection(self):
        cb = lambda p: None
        htf_signals.subscribe('test.list', cb)
        self.assertIn(cb, htf_signals.subscribers('test.list'))
