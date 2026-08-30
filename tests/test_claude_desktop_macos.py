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
