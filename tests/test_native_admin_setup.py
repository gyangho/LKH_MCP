"""Local administrator bootstrap is one-time and never stores raw password."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import io
import os
import subprocess
import sys
import native_admin_setup as setup

from native_admin_setup import initialize


class AdminSetupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "state"

    def test_initial_admin_is_hashed_and_never_overwritten(self):
        result = initialize(root=self.root, username="admin", password="ExampleLongPrivatePassword99!")
        self.assertTrue(result["configured"])
        self.assertFalse(result["unchanged"])
        p = self.root / "config" / "bootstrap.json"
        data = json.loads(p.read_text("utf-8"))
        self.assertNotIn("ExampleLongPrivatePassword99!", p.read_text("utf-8"))
        self.assertTrue(data["ADMIN_PASSWORD_HASH"].startswith("pbkdf2_sha256$"))
        self.assertEqual(data["ADMIN_PUBLIC_ORIGIN"], "http://127.0.0.1:8001")
        self.assertTrue(initialize(root=self.root)["unchanged"])
        self.assertEqual(json.loads(p.read_text("utf-8")), data)

    def test_rejects_short_password_without_config_file(self):
        with self.assertRaises(ValueError):
            initialize(root=self.root, username="admin", password="short")
        self.assertFalse((self.root / "config" / "bootstrap.json").exists())


    def test_installer_reads_credentials_from_stdin(self):
        raw = json.dumps({"username": "admin", "password": "비공개-암호-ExampleLong99!"}, ensure_ascii=True)
        with patch.object(setup.os, "name", "nt"), patch.object(setup.sys, "stdin", io.StringIO(raw)), patch.object(setup, "initialize", return_value={"unchanged": False}) as init:
            setup.main(["--initialize", "--stdin-json"])
            init.assert_called_once_with(username="admin", password="비공개-암호-ExampleLong99!")

    def test_installer_rejects_extra_payload_fields(self):
        raw = json.dumps({"username": "admin", "password": "long-secret", "path": "arbitrary"})
        with patch.object(setup.os, "name", "nt"), patch.object(setup.sys, "stdin", io.StringIO(raw)), patch.object(setup, "initialize") as init:
            with self.assertRaises(SystemExit):
                setup.main(["--initialize", "--stdin-json"])
            init.assert_not_called()

    def test_publication_never_replaces_a_concurrent_config(self):
        target = self.root / "config" / "bootstrap.json"
        def concurrent_writer(source, destination):
            target.write_text("existing-account", encoding="utf-8")
            raise FileExistsError("concurrent initialization")
        with patch.object(setup.os, "link", side_effect=concurrent_writer):
            with self.assertRaises(FileExistsError):
                initialize(root=self.root, password="ExampleLongPrivatePassword99!")
        self.assertEqual(target.read_text("utf-8"), "existing-account")


    @unittest.skipUnless(os.name == "nt", "Windows installer helper")
    def test_real_helper_receives_unicode_credentials_through_stdin_pipe(self):
        root = Path(__file__).resolve().parents[1]
        password = "Synthetic-pipe-only-秘密99!"
        result = subprocess.run([sys.executable, str(root / "scripts/native-admin-setup.py"), "--initialize", "--stdin-json"],
            input=json.dumps({"username": "installer-admin", "password": password}, ensure_ascii=True),
            text=True, capture_output=True, timeout=20,
            env={**os.environ, "PYTHONPATH": str(root / "src"), "LKH_NATIVE_STATE_DIR": str(self.root)})
        self.assertEqual(result.returncode, 0, "Installer helper failed")
        self.assertNotIn(password, result.stdout + result.stderr)
        content = (self.root / "config/bootstrap.json").read_text("utf-8")
        self.assertNotIn(password, content)
        self.assertEqual(json.loads(content)["ADMIN_LOGIN_USER"], "installer-admin")


if __name__ == "__main__":
    unittest.main()
