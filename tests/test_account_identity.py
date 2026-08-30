import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


def load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WINDOWS = load_module("ai_usage_widget_identity_windows", "src/ai_usage_widget.py")


class AccountIdentityTests(unittest.TestCase):
    def tearDown(self):
        WINDOWS._CLAUDE_OAUTH_CACHE.clear()

    def test_claude_profile_email_variants(self):
        self.assertEqual(
            WINDOWS.account_email({"account": {"email_address": "person@example.com"}}),
            "person@example.com",
        )

    def test_account_display_prefers_email_then_id(self):
        self.assertEqual(WINDOWS.account_display({"email": "me@example.com"}), "me@example.com")
        self.assertEqual(WINDOWS.account_display({"account_id": "user-123"}), "ID: user-123")

    def test_cursor_fetches_identity_without_breaking_usage(self):
        responses = [
            (200, {"individualUsage": {"plan": {"autoPercentUsed": 7}}}, None),
            (200, {"email": "cursor@example.com"}, None),
            (404, None, "not available"),
            (404, None, "not available"),
        ]
        with patch.object(WINDOWS, "cursor_session", return_value=("cookie", "user-id", None)), \
                patch.object(WINDOWS, "request_json", side_effect=responses):
            result = WINDOWS.get_cursor()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["email"], "cursor@example.com")

    def test_claude_refresh_stays_in_memory(self):
        response = (200, {"access_token": "new-access", "refresh_token": "new-refresh"}, None)
        with patch.object(WINDOWS, "request_form_json", return_value=response) as request:
            token = WINDOWS.refresh_claude_oauth({"refreshToken": "old-refresh"})
        self.assertEqual(token, "new-access")
        self.assertEqual(WINDOWS._CLAUDE_OAUTH_CACHE["refresh_token"], "new-refresh")
        self.assertEqual(request.call_args.args[1]["grant_type"], "refresh_token")


if __name__ == "__main__":
    unittest.main()
