"""Read locally stored Cursor and Claude logins without logging secrets.

Cursor desktop may store `cursorAuth/accessToken` as plaintext JWT or as
Electron safeStorage ciphertext (`cursor-safe-storage:v1:`). Sending the
ciphertext as a Bearer token produces HTTP 401.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
from pathlib import Path


SAFE_STORAGE_PREFIX = "cursor-safe-storage:v1:"


def is_jwt(value):
    if not isinstance(value, str) or value.count(".") != 2:
        return False
    return not value.startswith(SAFE_STORAGE_PREFIX)


def is_encrypted_cursor_secret(value):
    return isinstance(value, str) and value.startswith(SAFE_STORAGE_PREFIX)


def cursor_support_dir(platform_name=None, env=None, home=None):
    platform_name = platform_name or sys.platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "Cursor"
    if platform_name == "linux":
        return Path(env.get("XDG_CONFIG_HOME") or (home / ".config")) / "Cursor"
    appdata = env.get("APPDATA")
    base = Path(appdata) if appdata else home / "AppData" / "Roaming"
    return base / "Cursor"


def cursor_auth_json_paths(platform_name=None, env=None, home=None):
    platform_name = platform_name or sys.platform
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    paths = [cursor_support_dir(platform_name, env, home) / "auth.json"]
    paths.append(home / ".cursor" / "auth.json")
    if platform_name == "linux":
        paths.append(Path(env.get("XDG_CONFIG_HOME") or (home / ".config")) / "cursor" / "auth.json")
    else:
        paths.append(home / ".config" / "cursor" / "auth.json")
    return paths


def _dpapi_unprotect(blob):
    if sys.platform != "win32" or not blob:
        return None
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(blob, len(blob))
    blob_in = DATA_BLOB(len(blob), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 1, ctypes.byref(blob_out)):
        return None
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            kernel32.LocalFree(blob_out.pbData)


def _windows_os_crypt_key(support_dir):
    local_state = Path(support_dir) / "Local State"
    try:
        payload = json.loads(local_state.read_text(encoding="utf-8"))
        encoded = ((payload.get("os_crypt") or {}).get("encrypted_key"))
        raw = base64.b64decode(encoded)
    except Exception:
        return None
    if not raw.startswith(b"DPAPI"):
        return None
    key = _dpapi_unprotect(raw[5:])
    return key if key and len(key) == 32 else None


def _aes_gcm_decrypt(key, nonce, ciphertext_and_tag):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception:
        return None
    try:
        return AESGCM(key).decrypt(nonce, ciphertext_and_tag, None)
    except Exception:
        return None


def _aes_cbc_decrypt(key, iv, ciphertext):
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.primitives import padding
    except Exception:
        return None
    try:
        decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(len(key) * 8).unpadder()
        return unpadder.update(padded) + unpadder.finalize()
    except Exception:
        return None


def _macos_safe_storage_password():
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Cursor Safe Storage",
             "-a", "Cursor Key", "-w"],
            capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return None
    password = (result.stdout or "").strip()
    return password or None


def decrypt_electron_blob(blob, platform_name=None, support_dir=None):
    if not blob:
        return None
    platform_name = platform_name or sys.platform
    if blob.startswith(b"v10") and len(blob) > 31 and platform_name == "win32":
        key = _windows_os_crypt_key(support_dir)
        if not key:
            return None
        nonce = blob[3:15]
        payload = blob[15:]
        plain = _aes_gcm_decrypt(key, nonce, payload)
        return plain.decode("utf-8") if plain else None
    if blob.startswith(b"v10") and platform_name == "darwin":
        import hashlib
        password = _macos_safe_storage_password()
        if not password:
            return None
        key = hashlib.pbkdf2_hmac("sha1", password.encode("utf-8"), b"saltysalt", 1003, dklen=16)
        plain = _aes_cbc_decrypt(key, b" " * 16, blob[3:])
        return plain.decode("utf-8") if plain else None
    if platform_name == "win32":
        plain = _dpapi_unprotect(blob)
        if plain:
            try:
                return plain.decode("utf-8")
            except Exception:
                return None
    return None


def unwrap_cursor_secret(value, platform_name=None, env=None, home=None):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if is_jwt(value) or (value.startswith("eyJ") and "." in value):
        return value
    if not value.startswith(SAFE_STORAGE_PREFIX):
        return value if "." in value else None
    try:
        blob = base64.b64decode(value[len(SAFE_STORAGE_PREFIX):])
    except Exception:
        return None
    return decrypt_electron_blob(
        blob, platform_name=platform_name,
        support_dir=cursor_support_dir(platform_name, env, home))


def read_cursor_auth_json(platform_name=None, env=None, home=None):
    for path in cursor_auth_json_paths(platform_name, env, home):
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        token = data.get("accessToken") or data.get("access_token")
        refresh = data.get("refreshToken") or data.get("refresh_token")
        if isinstance(token, str) and token.strip():
            return token.strip(), (refresh.strip() if isinstance(refresh, str) else None)
    return None, None


def _windows_credential_struct():
    class FILETIME(ctypes.Structure):
        _fields_ = [("dwLowDateTime", ctypes.wintypes.DWORD),
                    ("dwHighDateTime", ctypes.wintypes.DWORD)]
    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", ctypes.wintypes.DWORD),
            ("Type", ctypes.wintypes.DWORD),
            ("TargetName", ctypes.wintypes.LPWSTR),
            ("Comment", ctypes.wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", ctypes.wintypes.DWORD),
            ("CredentialBlob", ctypes.c_void_p),
            ("Persist", ctypes.wintypes.DWORD),
            ("AttributeCount", ctypes.wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", ctypes.wintypes.LPWSTR),
            ("UserName", ctypes.wintypes.LPWSTR),
        ]
    return CREDENTIAL


def _decode_credential_blob(blob):
    for encoding in ("utf-16-le", "utf-8"):
        try:
            text = blob.decode(encoding)
            if "\x00" in text:
                text = text.replace("\x00", "")
            text = text.strip()
            if text.startswith("{") or "accessToken" in text or "refreshToken" in text:
                return text
        except Exception:
            continue
    return None


def windows_generic_credential(target):
    if sys.platform != "win32" or not target:
        return None
    advapi32 = ctypes.windll.advapi32
    CREDENTIAL = _windows_credential_struct()
    ptr = ctypes.c_void_p()
    if not advapi32.CredReadW(str(target), 1, 0, ctypes.byref(ptr)):
        return None
    try:
        cred = ctypes.cast(ptr, ctypes.POINTER(CREDENTIAL)).contents
        blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
    finally:
        advapi32.CredFree(ptr)
    return _decode_credential_blob(blob)


def windows_enumerate_claude_credentials():
    if sys.platform != "win32":
        return []
    advapi32 = ctypes.windll.advapi32
    CREDENTIAL = _windows_credential_struct()
    count = ctypes.wintypes.DWORD()
    array = ctypes.POINTER(ctypes.c_void_p)()
    found = []
    if not advapi32.CredEnumerateW(None, 0, ctypes.byref(count), ctypes.byref(array)):
        return []
    try:
        for index in range(count.value):
            cred = ctypes.cast(array[index], ctypes.POINTER(CREDENTIAL)).contents
            name = cred.TargetName or ""
            lowered = name.lower()
            if not any(token in lowered for token in ("claude", "anthropic")):
                continue
            blob = ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            text = _decode_credential_blob(blob)
            if text:
                found.append(text)
    finally:
        advapi32.CredFree(array)
    return found


def _claude_payload_usable(data):
    if not isinstance(data, dict):
        return False
    oauth = data.get("claudeAiOauth") if isinstance(data.get("claudeAiOauth"), dict) else {}
    token = oauth.get("accessToken") or oauth.get("access_token") or data.get("accessToken")
    refresh = oauth.get("refreshToken") or oauth.get("refresh_token") or data.get("refreshToken")
    return bool((isinstance(token, str) and token.strip()) or (isinstance(refresh, str) and refresh.strip()))


def claude_credentials_payload(env=None, home=None):
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    configured = env.get("CLAUDE_CONFIG_DIR")
    paths = []
    if configured:
        paths.append(Path(configured) / ".credentials.json")
    paths.append(home / ".claude" / ".credentials.json")
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if _claude_payload_usable(data):
            return data
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/bin/security", "find-generic-password", "-w", "-s", "Claude Code-credentials"],
                capture_output=True, text=True, timeout=5, check=True)
            data = json.loads(result.stdout)
            if _claude_payload_usable(data):
                return data
        except Exception:
            pass
    if sys.platform == "win32":
        for target in (
            "Claude Code-credentials", "Claude Code", "claude-code-credentials",
            "Claude", "Anthropic", "anthropic.com", "claude.ai",
        ):
            raw = windows_generic_credential(target)
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if _claude_payload_usable(data):
                return data
            wrapped = {"claudeAiOauth": data}
            if _claude_payload_usable(wrapped):
                return wrapped
        for raw in windows_enumerate_claude_credentials():
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            if _claude_payload_usable(data):
                return data
            wrapped = {"claudeAiOauth": data}
            if _claude_payload_usable(wrapped):
                return wrapped
    return None
