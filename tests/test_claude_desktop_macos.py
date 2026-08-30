import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "src" / "ai_usage_widget_macos.py"
SPEC = importlib.util.spec_from_file_location("ai_usage_widget_claude_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClaudeDesktopUsageTests(unittest.TestCase):
    def tearDown(self):
        MODULE._CLAUDE_OAUTH_CACHE.clear()

    def write_history(self, directory, timestamp, usage):
        Path(directory, "plan-usage-history.json").write_text(
            json.dumps({"version": 2, "samples": [{"t": timestamp, "org": "test", "u": usage}]}),
            encoding="utf-8",
        )

    def test_reads_most_constrained_current_desktop_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_history(directory, int(time.time() * 1000), {"fh": 12, "sd": 37})
            with patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": directory}):
                result = MODULE.get_claude_desktop()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["label"], "Wöchentlich")
        self.assertEqual(result["used"], 37)
        self.assertEqual([window["label"] for window in result["windows"]], ["5 Stunden", "Wöchentlich"])

    def test_rejects_stale_desktop_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_history(directory, int((time.time() - 1900) * 1000), {"fh": 12})
            with patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": directory}):
                result = MODULE.get_claude_desktop()
        self.assertEqual(result["status"], "error")
        self.assertIn("öffnen", result["message"])

    def test_account_identity_helpers(self):
        self.assertEqual(
            MODULE.account_email({"account": {"emailAddress": "mac@example.com"}}),
            "mac@example.com",
        )
        self.assertEqual(MODULE.account_display({"account_id": "mac-user"}), "ID: mac-user")

    def test_cursor_fetches_identity_without_breaking_usage(self):
        responses = [
            (200, {"individualUsage": {"plan": {"autoPercentUsed": 7}}}, None),
            (200, {"email": "cursor-mac@example.com"}, None),
            (404, None, "not available"),
            (404, None, "not available"),
        ]
        with patch.object(MODULE, "cursor_session", return_value=("cookie", "user-id", None)), \
                patch.object(MODULE, "request_json", side_effect=responses):
            result = MODULE.get_cursor()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["email"], "cursor-mac@example.com")

    def test_expired_claude_access_token_is_refreshed_in_memory(self):
        credentials = {"claudeAiOauth": {"accessToken": "expired", "refreshToken": "refresh"}}
        requests = [
            (401, None, "expired"),
            (200, {"account": {"email": "claude@example.com"}}, None),
            (200, {
                "five_hour": {"utilization": 12, "resets_at": "2026-09-01T01:00:00Z"},
                "seven_day": {"utilization": 34, "resets_at": "2026-09-07T01:00:00Z"},
            }, None),
        ]
        refresh = (200, {"access_token": "fresh", "refresh_token": "fresh-refresh"}, None)
        with patch.object(MODULE, "claude_credentials", return_value=credentials), \
                patch.object(MODULE, "request_json", side_effect=requests), \
                patch.object(MODULE, "request_form_json", return_value=refresh), \
                patch.object(MODULE, "get_claude_desktop", return_value={"status": "error"}):
            result = MODULE.get_claude()
        self.assertEqual(result["source"], "oauth")
        self.assertEqual(result["email"], "claude@example.com")
        self.assertEqual(result["windows"][0]["resets_at"], "2026-09-01T01:00:00Z")

    def test_oauth_extras_are_merged_with_desktop_windows(self):
        desktop = {"status": "ok", "source": "claude-desktop", "windows": [
            {"id": "claude-session-5h", "label": "5 Stunden", "used_percent": 10, "resets_at": None},
            {"id": "claude-weekly", "label": "Wöchentlich", "used_percent": 20, "resets_at": None},
        ]}
        live = {"status": "ok", "source": "oauth", "windows": [
            {"id": "claude-extra-usage", "label": "Extra Usage", "used_percent": 78, "resets_at": None},
        ]}
        result = MODULE.merge_claude_usage(live, desktop)
        self.assertEqual([window["label"] for window in result["windows"]],
                         ["5 Stunden", "Wöchentlich", "Extra Usage"])
        self.assertEqual(result["source"], "oauth+claude-desktop")

    def test_widget_snapshot_exposes_all_windows_without_credentials(self):
        app = object.__new__(MODULE.App)
        app.data = {
            "claude": {"status": "ok", "used": 44, "secret": "never-export",
                       "email": "private@example.com", "account_id": "private-id",
                       "windows": [
                           {"id": "session", "label": "5 Stunden", "type": "session",
                            "used_percent": 12, "resets_at": "2026-09-01T00:00:00Z"},
                           {"id": "weekly", "label": "Wöchentlich", "type": "weekly",
                            "used_percent": 44, "resets_at": None},
                       ]},
            "codex": {"status": "error"},
            "cursor": {"status": "ok", "cursor_models_used": 7, "other_models_used": 9},
        }
        snapshot = app.widget_snapshot()
        self.assertEqual(len(snapshot["providers"][0]["windows"]), 2)
        self.assertNotIn("never-export", json.dumps(snapshot))
        self.assertNotIn("private@example.com", json.dumps(snapshot))
        self.assertNotIn("private-id", json.dumps(snapshot))


if __name__ == "__main__":
    unittest.main()
