import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def install_import_stubs():
    requests = types.ModuleType("requests")
    requests.post = lambda *args, **kwargs: None
    requests.exceptions = types.SimpleNamespace(RequestException=Exception)

    httpx = types.ModuleType("httpx")
    httpx.post = lambda *args, **kwargs: None
    httpx.RequestError = Exception

    crypto = types.ModuleType("Crypto")
    cipher = types.ModuleType("Crypto.Cipher")
    aes = types.ModuleType("Crypto.Cipher.AES")
    aes.MODE_ECB = 1
    aes.block_size = 16
    aes.new = lambda *args, **kwargs: None
    util = types.ModuleType("Crypto.Util")
    padding = types.ModuleType("Crypto.Util.Padding")
    padding.pad = lambda data, *args, **kwargs: data

    sys.modules.setdefault("requests", requests)
    sys.modules.setdefault("httpx", httpx)
    sys.modules.setdefault("Crypto", crypto)
    sys.modules.setdefault("Crypto.Cipher", cipher)
    sys.modules.setdefault("Crypto.Cipher.AES", aes)
    sys.modules.setdefault("Crypto.Util", util)
    sys.modules.setdefault("Crypto.Util.Padding", padding)


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


install_import_stubs()
main_send_msg = load_module("main_send_msg", "scripts/main_send_msg.py")
main_send_file = load_module("main_send_file", "scripts/main_send_file.py")


class AccountConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write_account(self, root: Path, account_id: str, config: dict, context: dict | None = None):
        accounts = root / "accounts"
        accounts.mkdir(parents=True, exist_ok=True)
        (accounts / f"{account_id}.json").write_text(json.dumps(config), encoding="utf-8")
        if context is not None:
            (accounts / f"{account_id}.context-tokens.json").write_text(
                json.dumps(context),
                encoding="utf-8",
            )

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_auto_discovers_openclaw_account(self):
        account_id = "openclaw-account"
        openclaw_root = self.home / ".openclaw" / "openclaw-weixin"
        self.write_account(
            openclaw_root,
            account_id,
            {"token": "token", "userId": "user", "baseUrl": "https://example.invalid"},
            {"user": "context"},
        )

        with mock.patch("pathlib.Path.home", return_value=self.home):
            discovered = main_send_msg.find_weixin_account()
            account = main_send_msg.load_account_credentials(discovered.account_id)

        self.assertEqual(discovered.account_id, account_id)
        self.assertEqual(discovered.platform, "OpenClaw")
        self.assertEqual(account["token"], "token")
        self.assertEqual(account["user_id"], "user")
        self.assertEqual(account["context_token"], "context")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_auto_discovers_hermes_account(self):
        account_id = "hermes-account"
        hermes_root = self.home / ".hermes" / "weixin"
        self.write_account(
            hermes_root,
            account_id,
            {"token": "token", "user_id": "user"},
            {"user": "context"},
        )

        with mock.patch("pathlib.Path.home", return_value=self.home):
            discovered = main_send_file.find_weixin_account()
            account = main_send_file.load_account_credentials(discovered.account_id)

        self.assertEqual(discovered.account_id, account_id)
        self.assertEqual(discovered.platform, "Hermes Agent")
        self.assertEqual(account["base_url"], "https://ilinkai.weixin.qq.com")
        self.assertEqual(account["user_id"], "user")

    @mock.patch.dict(os.environ, {}, clear=True)
    def test_missing_required_credentials_returns_error(self):
        account_id = "broken-account"
        hermes_root = self.home / ".hermes" / "weixin"
        self.write_account(hermes_root, account_id, {"token": "token"}, {})

        with mock.patch("pathlib.Path.home", return_value=self.home):
            result = main_send_msg.load_account_credentials(account_id)

        self.assertIn("error", result)
        self.assertIn("user_id", result["error"])

    def test_file_prepare_rejects_missing_file(self):
        result = main_send_file.prepare_image_upload(str(self.home / "missing.png"))

        self.assertFalse(result["success"])
        self.assertIn("文件不存在", result["error"])

    def test_file_send_rejects_missing_file_before_network(self):
        with mock.patch.object(sys.modules["requests"], "post") as post:
            stdout = io.StringIO()
            with mock.patch("sys.stdout", stdout):
                result = main_send_file.send_weixin_file(
                    "token",
                    "user",
                    "context",
                    str(self.home / "missing.png"),
                )

        self.assertFalse(result)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
