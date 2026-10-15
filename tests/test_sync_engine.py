import os
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from garoon_google_sync_gui import ConfigManager, GaroonToGoogleSync

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


class TestConfigManagerDefaults(unittest.TestCase):
    def test_default_config_enables_notifications(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = os.path.join(tmp, "sync_config.json")
            manager = ConfigManager(config_path)
            config = manager.load()
            self.assertTrue(config["enable_notifications"])


class TestGaroonToGoogleSyncNotificationWiring(unittest.TestCase):
    def test_constructor_stores_enable_notifications_false(self):
        engine = GaroonToGoogleSync(garoon=None, google=None, db=None, enable_notifications=False)
        self.assertFalse(engine.enable_notifications)

    def test_constructor_defaults_enable_notifications_true(self):
        engine = GaroonToGoogleSync(garoon=None, google=None, db=None)
        self.assertTrue(engine.enable_notifications)

    def test_add_to_google_respects_disabled_notifications(self):
        mock_google = Mock()
        mock_google.create_event.return_value = {"id": "g1", "updated": "2026-10-15T01:00:00Z"}
        mock_db = Mock()
        engine = GaroonToGoogleSync(garoon=None, google=mock_google, db=mock_db,
                                    log_callback=lambda *_: None, enable_notifications=False)
        engine._add_to_google(SAMPLE_EVENT)
        sent_event = mock_google.create_event.call_args[0][0]
        self.assertEqual(sent_event["reminders"], {"useDefault": False, "overrides": []})

    def test_update_google_from_garoon_respects_disabled_notifications(self):
        mock_google = Mock()
        mock_google.update_event.return_value = {"id": "g1", "updated": "2026-10-15T01:00:00Z"}
        mock_db = Mock()
        engine = GaroonToGoogleSync(garoon=None, google=mock_google, db=mock_db,
                                    log_callback=lambda *_: None, enable_notifications=False)
        engine._update_google_from_garoon(SAMPLE_EVENT, google_id="g1")
        sent_event = mock_google.update_event.call_args[0][1]
        self.assertEqual(sent_event["reminders"], {"useDefault": False, "overrides": []})


if __name__ == "__main__":
    unittest.main()
