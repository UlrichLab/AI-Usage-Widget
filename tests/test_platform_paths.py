import importlib.util
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
