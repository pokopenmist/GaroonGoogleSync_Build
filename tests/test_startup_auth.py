import os
import pickle
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import garoon_google_sync_gui as app
from garoon_google_sync_gui import SyncApp


class FakeCreds:
    def __init__(self, valid=False, expired=False, refresh_token=None):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token


class TestStartupAuthWorker(unittest.TestCase):
    """起動時のGoogle認証確認（別スレッド側）はUIに触らず、結果を root.after で返す"""

    def _run_worker(self, creds, fetch=None):
        with tempfile.TemporaryDirectory() as tmp:
            token = os.path.join(tmp, "token.pickle")
            if creds is not None:
                with open(token, "wb") as f:
                    pickle.dump(creds, f)
            fake = Mock()
            fake._fetch_calendar_names = fetch or Mock(return_value=["Garoon", "仕事"])
            with patch.object(app, "TOKEN_FILE", token):
                SyncApp._check_google_auth_worker(fake)
            callback, *args = fake.root.after.call_args[0][1:]
            return callback, args, fake

    def test_valid_token_returns_ok_with_calendars(self):
        callback, args, fake = self._run_worker(FakeCreds(valid=True))
        self.assertIs(callback, fake._apply_google_auth_result)
        self.assertEqual(args, ["ok", ["Garoon", "仕事"], None])

    def test_expired_without_refresh_token_returns_expired(self):
        _, args, fake = self._run_worker(FakeCreds(expired=True))
        self.assertEqual(args, ["expired", None, None])
        fake._fetch_calendar_names.assert_not_called()

    def test_calendar_fetch_error_is_passed_back(self):
        error = RuntimeError("network")
        _, args, _ = self._run_worker(FakeCreds(valid=True), fetch=Mock(side_effect=error))
        self.assertEqual(args, ["ok", None, error])

    def test_unreadable_token_returns_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            token = os.path.join(tmp, "token.pickle")
            with open(token, "wb") as f:
                f.write(b"broken")
            fake = Mock()
            with patch.object(app, "TOKEN_FILE", token):
                SyncApp._check_google_auth_worker(fake)
            self.assertEqual(list(fake.root.after.call_args[0][2:]), ["missing", None, None])


class TestApplyGoogleAuthResult(unittest.TestCase):
    def test_ok_marks_authenticated_and_sets_calendars(self):
        fake = Mock()
        SyncApp._apply_google_auth_result(fake, "ok", ["Garoon"], None)
        self.assertTrue(fake.google_authenticated)
        self.assertFalse(fake.google_auth_checking)
        fake.google_status_var.set.assert_called_with("✅ 認証済み")
        fake._set_calendar_names.assert_called_once_with(["Garoon"])

    def test_ok_with_calendar_error_logs(self):
        fake = Mock()
        SyncApp._apply_google_auth_result(fake, "ok", None, RuntimeError("network"))
        self.assertTrue(fake.google_authenticated)
        fake._log.assert_called_once()
        fake._set_calendar_names.assert_not_called()

    def test_expired_and_missing(self):
        for status, label in (("expired", "⚠️ 要再認証"), ("missing", "❌ 未認証")):
            fake = Mock()
            SyncApp._apply_google_auth_result(fake, status, None, None)
            self.assertFalse(fake.google_authenticated)
            self.assertFalse(fake.google_auth_checking)
            fake.google_status_var.set.assert_called_with(label)


class TestLazyGoogleImports(unittest.TestCase):
    def test_module_import_does_not_load_google_auth(self):
        import subprocess
        code = ("import sys; sys.path.insert(0, r'%s'); import garoon_google_sync_gui; "
                "print(any(m.startswith(('google.auth', 'google_auth_oauthlib', 'cryptography')) for m in sys.modules))"
                % os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
