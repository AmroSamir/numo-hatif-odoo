"""htf.webhook.event — dedup, mark_processed, purge."""

from datetime import timedelta

from odoo import fields

from .common import HtfTransactionCase


class TestWebhookEvent(HtfTransactionCase):

    def test_record_first_delivery_returns_record(self):
        rec = self.env['htf.webhook.event'].record_or_skip(
            'evt-1', 'whatsapp', b'{"x": 1}'
        )
        self.assertTrue(rec)
        self.assertEqual(rec.event_id, 'evt-1')
        self.assertEqual(rec.route, 'whatsapp')
        self.assertTrue(rec.payload_hash)
        self.assertEqual(len(rec.payload_hash), 64)

    def test_duplicate_returns_false(self):
        first = self.env['htf.webhook.event'].record_or_skip('evt-2', 'whatsapp')
        self.assertTrue(first)
        dup = self.env['htf.webhook.event'].record_or_skip('evt-2', 'whatsapp')
        self.assertFalse(dup)

    def test_same_event_different_route_not_duplicate(self):
        a = self.env['htf.webhook.event'].record_or_skip('evt-3', 'whatsapp')
        b = self.env['htf.webhook.event'].record_or_skip('evt-3', 'call')
        self.assertTrue(a)
        self.assertTrue(b)
        self.assertNotEqual(a.id, b.id)

    def test_missing_event_id_returns_empty_recordset(self):
        rec = self.env['htf.webhook.event'].record_or_skip('', 'whatsapp')
        self.assertFalse(rec)

    def test_missing_route_returns_empty_recordset(self):
        rec = self.env['htf.webhook.event'].record_or_skip('evt-4', '')
        self.assertFalse(rec)

    def test_mark_processed_updates_flag(self):
        rec = self.env['htf.webhook.event'].record_or_skip('evt-5', 'whatsapp')
        self.env['htf.webhook.event'].mark_processed(rec.id, note='handled')
        rec.invalidate_recordset()
        self.assertTrue(rec.processed)
        self.assertEqual(rec.note, 'handled')

    def test_mark_processed_with_no_id_noop(self):
        # Should not raise.
        self.env['htf.webhook.event'].mark_processed(0)
        self.env['htf.webhook.event'].mark_processed(False)

    def test_cron_purge_removes_old_rows(self):
        rec = self.env['htf.webhook.event'].record_or_skip('evt-old', 'whatsapp')
        # Backdate by 100 days.
        rec.received_at = fields.Datetime.now() - timedelta(days=100)
        deleted = self.env['htf.webhook.event'].cron_purge_old(days=90)
        self.assertEqual(deleted, 1)
        self.assertFalse(rec.exists())

    def test_cron_purge_keeps_fresh_rows(self):
        rec = self.env['htf.webhook.event'].record_or_skip('evt-fresh', 'whatsapp')
        deleted = self.env['htf.webhook.event'].cron_purge_old(days=90)
        self.assertEqual(deleted, 0)
        self.assertTrue(rec.exists())
