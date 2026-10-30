"""Local administrator bootstrap is one-time and never stores raw password."""
import json
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(data["ADMIN_PUBLIC_ORIGIN"], "http://127.0.0.1:18081")
        self.assertTrue(initialize(root=self.root)["unchanged"])
        self.assertEqual(json.loads(p.read_text("utf-8")), data)

    def test_rejects_short_password_without_config_file(self):
        with self.assertRaises(ValueError):
            initialize(root=self.root, username="admin", password="short")
        self.assertFalse((self.root / "config" / "bootstrap.json").exists())


if __name__ == "__main__":
    unittest.main()
