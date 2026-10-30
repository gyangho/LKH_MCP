"""SQLite config regression tests: persistence, validation, and revision guards."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import settings_store


class TestSettingsStore(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "config.sqlite3"
        e = patch.dict(os.environ, {"MCP_DB_PATH": str(self.path),
                                    "MCP_BOOTSTRAP_FILE": str(Path(tmp.name) / "missing.json"),
                                    "GIT_ALLOW_PUSH": "false", "GIT_ALLOW_COMMIT": "false",
                                    "CODEX_DELEGATION_ENABLED": "false"}, clear=True)
        e.start()
        self.addCleanup(e.stop)
        dotenv_mock = patch("dotenv.load_dotenv", return_value=False)
        dotenv_mock.start()
        self.addCleanup(dotenv_mock.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))

    def test_defaults_and_persistence(self):
        self.assertFalse(settings_store.get("GIT_ALLOW_PUSH"))
        item = next(x for x in settings_store.items() if x["key"] == "GIT_ALLOW_PUSH")
        saved = settings_store.update("GIT_ALLOW_PUSH", True, "admin@example.test", item["revision"])
        self.assertTrue(saved["saved"])
        self.assertTrue(settings_store.get("GIT_ALLOW_PUSH"))
        self.assertEqual(os.environ["GIT_ALLOW_PUSH"], "true")
        settings_store._READY = False
        settings_store.initialize()
        self.assertTrue(settings_store.get("GIT_ALLOW_PUSH"))

    def test_project_names_accept_spacing_but_not_duplicates(self):
        good = "ITAM=gyangho/ITAM; LKH_MCP=gyangho/LKH_MCP"
        self.assertEqual(settings_store._validate("GIT_ALLOWED_REPOS", good), good)
        for bad in ("ITAM=gyangho/ITAM;ITAM=gyangho/ITAM", "ITAM=gyangho/ITAM;", "ITAM= "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                settings_store._validate("GIT_ALLOWED_REPOS", bad)

    def test_rejects_unapproved_keys_and_wrong_types(self):
        with self.assertRaises(ValueError):
            settings_store.update("ORACLE_PASSWORD", "leak", "admin@example.test", 1)
        with self.assertRaises(ValueError):
            settings_store.update("GIT_ALLOW_PUSH", "true", "admin@example.test", 1)
        with self.assertRaises(ValueError):
            settings_store.update("CODEX_MAX_RUNS_PER_DAY", 999, "admin@example.test", 1)

    def test_stale_revision_rejected(self):
        first = next(x for x in settings_store.items() if x["key"] == "CODEX_MAX_RUNS_PER_DAY")
        settings_store.update(first["key"], 3, "admin@example.test", first["revision"])
        with self.assertRaises(ValueError):
            settings_store.update(first["key"], 4, "admin@example.test", first["revision"])
        self.assertEqual(settings_store.get(first["key"]), 3)

    def test_secrets_are_not_in_database(self):
        settings_store.initialize()
        raw = self.path.read_bytes()
        self.assertNotIn(b"ORACLE_PASSWORD", raw)
        self.assertNotIn(b"ADMIN_CF_AUD", raw)

    def test_audit_tracks_setting_key_not_secrets(self):
        rev = next(x["revision"] for x in settings_store.items() if x["key"] == "GRAPHIFY_ALLOW_UPDATE")
        settings_store.update("GRAPHIFY_ALLOW_UPDATE", True, "admin@example.test", rev)
        audit = settings_store.audit_events()
        self.assertEqual(audit[0]["key"], "GRAPHIFY_ALLOW_UPDATE")
        self.assertNotIn("ORACLE_PASSWORD", str(audit))


if __name__ == "__main__":
    unittest.main()
