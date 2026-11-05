import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "src" / "ai_usage_widget.py"
SPEC = importlib.util.spec_from_file_location("ai_usage_widget", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CursorDatabasePathTests(unittest.TestCase):
    def test_windows_uses_appdata(self):
        path = MODULE.cursor_db_path(
            platform_name="win32",
            env={"APPDATA": r"C:\Users\Example\AppData\Roaming"},
            home=Path(r"C:\Users\Example"),
        )
        self.assertEqual(
            path,
            Path(r"C:\Users\Example\AppData\Roaming")
            / "Cursor"
            / "User"
            / "globalStorage"
            / "state.vscdb",
        )

    def test_macos_uses_application_support(self):
        path = MODULE.cursor_db_path(
            platform_name="darwin",
            env={},
            home=Path("/Users/example"),
        )
        self.assertEqual(
            path,
            Path("/Users/example/Library/Application Support/Cursor/User/globalStorage/state.vscdb"),
        )

    def test_cursor_user_id_prefers_user_prefix(self):
        self.assertEqual(MODULE.cursor_user_id("github|user_01ABCDEFGH"), "user_01ABCDEFGH")
        self.assertEqual(MODULE.cursor_user_id("user_01ABCDEFGH"), "user_01ABCDEFGH")

    def test_parse_reset_accepts_epoch_milliseconds(self):
        parsed = MODULE.parse_reset("1774846800000")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2026)

    def test_session_reads_db_when_path_contains_spaces(self):
        import base64
        import json
        import sqlite3
        import tempfile

        def fake_jwt():
            def part(payload):
                raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
            return f"{part({'alg':'none'})}.{part({'sub':'auth0|user_01SPACEPATH','email':'dev@example.com'})}.sig"

        token = fake_jwt()
        with tempfile.TemporaryDirectory(prefix="Felix Ulrich ") as directory:
            db = Path(directory) / "state.vscdb"
            con = sqlite3.connect(str(db))
            con.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
            con.execute("INSERT INTO ItemTable VALUES (?, ?)", ("cursorAuth/accessToken", token))
            con.commit()
            con.close()
            with patch.object(MODULE, "cursor_db_path", return_value=db):
                cookie, sub, email, access = MODULE.cursor_session()
        self.assertTrue(cookie.startswith("user_01SPACEPATH%3A%3A"))
        self.assertEqual(sub, "auth0|user_01SPACEPATH")
        self.assertEqual(email, "dev@example.com")
        self.assertEqual(access, token)

    def test_windows_reads_claude_data_cache_even_when_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "plan-usage-history.json").write_text(json.dumps({
                "version": 2,
                "samples": [
                    {"t": int((time.time() - 3600) * 1000), "u": {}},
                    {"t": int((time.time() - 1900) * 1000), "u": {"fh": 8, "sd": 21}},
                ],
            }), encoding="utf-8")
            with patch.dict(os.environ, {"CLAUDE_DESKTOP_DATA_DIR": directory}):
                result = MODULE.get_claude_desktop()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["stale"])
        self.assertEqual([window["label"] for window in result["windows"]], ["5 hours", "Weekly"])
        self.assertEqual(result["used"], 21)

    def test_windows_claude_data_dir_is_preferred(self):
        with tempfile.TemporaryDirectory() as directory:
            local = Path(directory) / "Local"
            package = local / "Claude-Data" / "claude_storepkg"
            package.mkdir(parents=True)
            env = {
                "LOCALAPPDATA": str(local),
                "APPDATA": str(Path(directory) / "Roaming"),
            }
            with patch.object(MODULE.sys, "platform", "win32"), patch.dict(os.environ, env, clear=False):
                os.environ.pop("CLAUDE_DESKTOP_DATA_DIR", None)
                dirs = MODULE.claude_desktop_data_dirs()
        self.assertEqual(dirs[0], package)


if __name__ == "__main__":
    unittest.main()
