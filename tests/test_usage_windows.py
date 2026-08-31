import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.usage_windows import normalize_claude_desktop, normalize_claude_usage, normalize_codex_usage


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("ai_usage_widget_windows_test", ROOT / "src" / "ai_usage_widget.py")
WINDOWS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WINDOWS)


class ClaudeUsageWindowTests(unittest.TestCase):
    def test_only_session(self):
        result = normalize_claude_usage({"five_hour": {"utilization": 12}})
        self.assertEqual([window["id"] for window in result["windows"]], ["claude-session-5h"])

    def test_session_and_week(self):
        result = normalize_claude_usage({
            "five_hour": {"utilization": 12},
            "seven_day": {"utilization": 37},
        })
        self.assertEqual([window["type"] for window in result["windows"]], ["session", "weekly"])

    def test_session_week_and_sonnet(self):
        result = normalize_claude_usage({
            "five_hour": {"utilization": 12},
            "seven_day": {"utilization": 37},
            "seven_day_sonnet": {"utilization": 55},
        })
        self.assertEqual(result["windows"][2]["label"], "Sonnet · Wöchentlich")

    def test_session_week_and_opus(self):
        result = normalize_claude_usage({
            "five_hour": {"utilization": 12},
            "seven_day": {"utilization": 37},
            "seven_day_opus": {"utilization": 66},
        })
        self.assertEqual(result["windows"][2]["model"], "Opus")

    def test_multiple_weekly_scoped_limits_are_dynamic(self):
        result = normalize_claude_usage({
            "five_hour": {"utilization": 12},
            "limits": [
                {"kind": "weekly_scoped", "group": "weekly", "percent": 5,
                 "scope": {"model": {"id": "fable-5", "display_name": "Fable"}}},
                {"kind": "weekly_scoped", "group": "weekly", "percent": 29,
                 "scope": {"model": {"id": "research-v2", "display_name": "Research"}}},
            ],
        })
        labels = [window["label"] for window in result["windows"]]
        self.assertEqual(labels, ["5 Stunden", "Fable · Wöchentlich", "Research · Wöchentlich"])

    def test_missing_fields_do_not_create_zero_percent_windows(self):
        result = normalize_claude_usage({
            "five_hour": None,
            "seven_day": {"resets_at": "2026-09-01T00:00:00Z"},
            "seven_day_opus": {"utilization": None},
        })
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["windows"], [])

    def test_inactive_opaque_backend_lane_is_hidden(self):
        result = normalize_claude_usage({
            "five_hour": {"utilization": 12},
            "nimbus_quill": {
                "utilization": 0,
                "resets_at": None,
                "limit_dollars": None,
                "used_dollars": None,
                "remaining_dollars": None,
                "locked_reason": None,
            },
        })
        self.assertEqual([window["label"] for window in result["windows"]], ["5 Stunden"])

    def test_unknown_new_scope_is_preserved(self):
        result = normalize_claude_usage({
            "limits": [{"kind": "weekly_scoped", "group": "weekly", "percent": 48,
                        "resets_at": "2026-09-01T00:00:00Z",
                        "scope": {"model": {"id": "future/model", "display_name": "Future Model"}}}],
        })
        self.assertEqual(result["windows"][0]["id"], "claude-weekly-scoped-future-model")
        self.assertEqual(result["windows"][0]["used_percent"], 48)

    def test_legacy_scoped_shape_is_also_preserved(self):
        result = normalize_claude_usage({
            "limits": [{"type": "weekly_scoped", "group": "weekly", "utilization": 31,
                        "scope": "new-model"}],
        })
        self.assertEqual(result["windows"][0]["label"], "New Model · Wöchentlich")
        self.assertEqual(result["windows"][0]["used_percent"], 31)

    def test_desktop_cache_keeps_every_available_lane(self):
        result = normalize_claude_desktop({"fh": 11, "sd": 22, "sn": 33, "new": 44})
        self.assertEqual(len(result["windows"]), 4)
        self.assertEqual(result["source"], "claude-desktop")

    def test_windows_desktop_cache_is_used_when_oauth_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "plan-usage-history.json").write_text(json.dumps({
                "samples": [{"t": int(time.time() * 1000), "u": {"fh": 12, "sd": 34}}]
            }), encoding="utf-8")
            with patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": directory}), \
                    patch.object(WINDOWS, "claude_credentials", return_value={"claudeAiOauth": {"accessToken": "token"}}), \
                    patch.object(WINDOWS, "request_json", return_value=(429, None, "rate limited")):
                result = WINDOWS.get_claude()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["source"], "claude-desktop")
        self.assertEqual(result["windows"][1]["used_percent"], 34)


class CodexUsageWindowTests(unittest.TestCase):
    def test_month_length_is_labeled_monthly(self):
        result = normalize_codex_usage({
            "rate_limit": {"primary_window": {
                "used_percent": 25,
                "limit_window_seconds": 30 * 86400,
            }},
        })
        self.assertEqual(result["windows"][0]["label"], "Monatlich")
        self.assertEqual(result["windows"][0]["type"], "monthly")

    def test_duration_controls_labels_and_order(self):
        result = normalize_codex_usage({
            "plan_type": "pro",
            "rate_limit": {
                "primary_window": {"used_percent": 43, "limit_window_seconds": 604800},
                "secondary_window": {"used_percent": 17, "limit_window_seconds": 18000},
            },
        })
        self.assertEqual([window["label"] for window in result["windows"]], ["5 Stunden", "Wöchentlich"])
        self.assertEqual(result["plan"], "pro")

    def test_additional_model_limits_are_dynamic_and_lossy(self):
        result = normalize_codex_usage({
            "rate_limit": {"primary_window": {"used_percent": 10, "limit_window_seconds": 18000}},
            "additional_rate_limits": [
                "malformed",
                {"limit_name": "GPT-5.3-Codex-Spark", "metered_feature": "gpt_5_3_codex_spark",
                 "rate_limit": {
                     "primary_window": {"used_percent": 30, "limit_window_seconds": 18000},
                     "secondary_window": {"used_percent": 80, "limit_window_seconds": 604800},
                 }},
            ],
        })
        labels = [window["label"] for window in result["windows"]]
        self.assertEqual(labels, [
            "5 Stunden",
            "GPT-5.3-Codex-Spark · 5 Stunden",
            "GPT-5.3-Codex-Spark · Wöchentlich",
        ])


if __name__ == "__main__":
    unittest.main()
