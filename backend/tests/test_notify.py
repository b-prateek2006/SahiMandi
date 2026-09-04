from datetime import datetime
import unittest

from app.models import Notification
from app.notify import MockGateway, message_for, process_queued_notifications


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def scalars(self, statement):
        return FakeResult(self.rows)

    def commit(self):
        self.committed = True


class FailingGateway:
    def send(self, phone, body):
        raise RuntimeError("gateway failure")


class NotificationTests(unittest.TestCase):
    def test_mock_delivery_marks_queued_notification_sent_with_timestamp(self):
        row = Notification(id=1, phone="9000000001", body="Test", status="QUEUED")
        session = FakeSession([row])

        count = process_queued_notifications(lambda: session, MockGateway())

        self.assertEqual(count, 1)
        self.assertEqual(row.status, "SENT")
        self.assertIsInstance(row.sent_at, datetime)
        self.assertTrue(session.committed)

    def test_failed_delivery_marks_notification_failed(self):
        row = Notification(id=1, phone="9000000001", body="Test", status="QUEUED")

        process_queued_notifications(lambda: FakeSession([row]), FailingGateway())

        self.assertEqual(row.status, "FAILED")
        self.assertIsNone(row.sent_at)

    def test_all_specified_templates_are_bilingual_and_under_160_characters(self):
        payload = {"centre": "Sehore", "date": "2026-09-04", "hour": 9, "qtl": 20, "token": 4, "ahead": 2, "wait": 24, "gross": 20, "grade": "A", "moisture": 12, "net": 19, "amount": 4000, "mill": "Mill 1", "reference": "REF1", "alt": "Ashta", "alt_date": "2026-09-05"}
        for kind in ("BOOKED", "ARRIVED", "WEIGHED", "GRADED", "LIFTED", "SETTLED", "CHOKED"):
            message = message_for(kind, 10, payload)
            self.assertLess(len(message), 160)
            self.assertIn("।", message)

    def test_choked_template_includes_centre_date_and_alternative(self):
        message = message_for("CHOKED", None, {"centre": "Sehore", "date": "2026-09-04", "alt": "Ashta", "alt_date": "2026-09-05"})

        self.assertIn("Sehore", message)
        self.assertIn("2026-09-04", message)
        self.assertIn("Ashta", message)
        self.assertIn("2026-09-05", message)
