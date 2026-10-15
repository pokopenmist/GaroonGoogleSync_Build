import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from garoon_google_sync_gui import EventConverter

SAMPLE_EVENT = {
    "id": "123",
    "subject": "テスト予定",
    "eventMenu": "",
    "eventType": "REGULAR",
    "isAllDay": False,
    "notes": "",
    "updatedAt": "2026-10-15T01:00:00Z",
    "start": {"dateTime": "2026-10-20T10:00:00+09:00"},
    "end": {"dateTime": "2026-10-20T11:00:00+09:00"},
}


class TestGaroonToGoogleNotifications(unittest.TestCase):
    def test_enable_notifications_true_omits_reminders(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT, enable_notifications=True)
        self.assertIsNotNone(result)
        self.assertNotIn("reminders", result)

    def test_enable_notifications_false_sets_no_reminders(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT, enable_notifications=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["reminders"], {"useDefault": False, "overrides": []})

    def test_enable_notifications_defaults_to_true(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT)
        self.assertIsNotNone(result)
        self.assertNotIn("reminders", result)


if __name__ == "__main__":
    unittest.main()
