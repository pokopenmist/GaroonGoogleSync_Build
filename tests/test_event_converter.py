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

SAMPLE_REPEATING_EVENT = {
    "id": "456",
    "subject": "定例会議",
    "eventMenu": "",
    "eventType": "REPEATING",
    "isAllDay": False,
    "notes": "",
    "updatedAt": "2026-10-15T01:00:00Z",
    "start": {"dateTime": "2026-10-20T10:00:00+09:00"},
    "end": {"dateTime": "2026-10-20T11:00:00+09:00"},
    "repeatInfo": {"type": "EVERY_WEEK", "dayOfWeek": "TUE"},
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


class TestGaroonToGoogleNotificationsRepeating(unittest.TestCase):
    def test_enable_notifications_false_with_repeating_event(self):
        result = EventConverter.garoon_to_google(SAMPLE_REPEATING_EVENT, enable_notifications=False)
        self.assertIsNotNone(result)
        self.assertEqual(result["reminders"], {"useDefault": False, "overrides": []})
        self.assertIn("recurrence", result)


class TestGaroonToGoogleFacilities(unittest.TestCase):
    def test_facilities_set_location(self):
        event = dict(SAMPLE_EVENT, facilities=[
            {"id": "1", "code": "room1", "name": "第1会議室"},
            {"id": "2", "code": "room2", "name": "第2会議室"},
        ])
        result = EventConverter.garoon_to_google(event)
        self.assertEqual(result["location"], "第1会議室, 第2会議室")

    def test_no_facilities_omits_location(self):
        result = EventConverter.garoon_to_google(SAMPLE_EVENT)
        self.assertNotIn("location", result)

    def test_empty_facilities_omits_location(self):
        event = dict(SAMPLE_EVENT, facilities=[])
        result = EventConverter.garoon_to_google(event)
        self.assertNotIn("location", result)

    def test_get_garoon_location(self):
        event = dict(SAMPLE_EVENT, facilities=[{"id": "1", "name": "応接室"}, {"id": "2", "name": ""}])
        self.assertEqual(EventConverter.get_garoon_location(event), "応接室")


if __name__ == "__main__":
    unittest.main()
