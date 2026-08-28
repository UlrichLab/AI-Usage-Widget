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
        self.assertEqual(result["label"], "7d-Limit")
        self.assertEqual(result["used"], 37)

    def test_rejects_stale_desktop_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_history(directory, int((time.time() - 1900) * 1000), {"fh": 12})
            with patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": directory}):
                result = MODULE.get_claude_desktop()
        self.assertEqual(result["status"], "error")
        self.assertIn("öffnen", result["message"])


if __name__ == "__main__":
    unittest.main()
