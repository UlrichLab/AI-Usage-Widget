import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.local_auth import (
    claude_credentials_payload,
    is_encrypted_cursor_secret,
    is_jwt,
    unwrap_cursor_secret,
)


class LocalAuthTests(unittest.TestCase):
    def test_jwt_detection(self):
        self.assertTrue(is_jwt("aaa.bbb.ccc"))
        self.assertFalse(is_jwt("cursor-safe-storage:v1:abc"))
        self.assertTrue(is_encrypted_cursor_secret("cursor-safe-storage:v1:abc"))

    def test_unwrap_keeps_plain_jwt(self):
        token = "aaa.bbb.ccc"
        self.assertEqual(unwrap_cursor_secret(token), token)

    def test_encrypted_blob_is_not_returned_as_bearer_token(self):
        value = "cursor-safe-storage:v1:" + base64.b64encode(b"not-a-token").decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            result = unwrap_cursor_secret(
                value, platform_name="win32", env={"APPDATA": directory}, home=directory)
        self.assertIsNone(result)

    @patch("src.local_auth.windows_generic_credential", return_value=None)
    @patch("src.local_auth.windows_enumerate_claude_credentials", return_value=[])
    def test_empty_claude_file_is_ignored(self, *_args):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".credentials.json"
            path.write_text(json.dumps({
                "claudeAiOauth": {"accessToken": "", "refreshToken": "", "expiresAt": 1}
            }), encoding="utf-8")
            data = claude_credentials_payload(env={"CLAUDE_CONFIG_DIR": directory}, home=directory)
        self.assertIsNone(data)

    def test_claude_file_credentials_are_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".credentials.json"
            path.write_text(json.dumps({
                "claudeAiOauth": {"accessToken": "token", "refreshToken": "refresh"}
            }), encoding="utf-8")
            data = claude_credentials_payload(env={"CLAUDE_CONFIG_DIR": directory}, home=directory)
        self.assertEqual(data["claudeAiOauth"]["accessToken"], "token")


if __name__ == "__main__":
    unittest.main()
