"""SQLite settings tests: current keys, legacy exclusion, revision guard."""
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
        e = patch.dict(os.environ, {
            "MCP_DB_PATH": str(self.path),
            "MCP_BOOTSTRAP_FILE": str(Path(tmp.name) / "missing.json"),
        }, clear=True)
        e.start()
        self.addCleanup(e.stop)
        p = patch("dotenv.load_dotenv", return_value=False)
        p.start()
        self.addCleanup(p.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))

    def test_defaults_and_persistence(self):
        self.assertFalse(settings_store.get("CODEX_AGENT_ENABLED"))
        item = next(x for x in settings_store.items() if x["key"] == "CODEX_AGENT_ENABLED")
        saved = settings_store.update("CODEX_AGENT_ENABLED", True, "admin@example.test", item["revision"])
        self.assertTrue(saved["saved"])
        self.assertTrue(settings_store.get("CODEX_AGENT_ENABLED"))
        settings_store._READY = False
        settings_store.initialize()
        self.assertTrue(settings_store.get("CODEX_AGENT_ENABLED"))

    def test_repository_allowlist_validation(self):
        good = "ITAM=gyangho/ITAM; LKH_MCP=gyangho/LKH_MCP"
        self.assertEqual(settings_store._validate("GIT_ALLOWED_REPOS", good), good)
        for bad in ("ITAM=gyangho/ITAM;ITAM=gyangho/ITAM", "ITAM=gyangho/ITAM;", "ITAM= "):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                settings_store._validate("GIT_ALLOWED_REPOS", bad)

    def test_legacy_keys_not_exposed_or_writable(self):
        retired = ("GIT_ALLOW_PUSH", "GIT_ALLOW_COMMIT", "GIT_EXECUTABLE",
                   "GRAPHIFY_ALLOW_UPDATE", "GRAPHIFY_PROJECTS",
                   "GRAPHIFY_EXECUTABLE", "CODEX_DELEGATION_ENABLED")
        self.assertFalse(set(retired) & {x["key"] for x in settings_store.items()})
        for key in retired:
            with self.subTest(key=key), self.assertRaises(ValueError):
                settings_store.update(key, True, "admin@example.test", 1)
        with self.assertRaises(ValueError):
            settings_store.update("ORACLE_PASSWORD", "secret", "admin@example.test", 1)

    def test_wrong_type_and_quota(self):
        with self.assertRaises(ValueError):
            settings_store.update("CODEX_AGENT_ENABLED", "true", "admin", 1)
        with self.assertRaises(ValueError):
            settings_store.update("CODEX_MAX_RUNS_PER_DAY", 999, "admin", 1)

    def test_revision_and_audit(self):
        item = next(x for x in settings_store.items() if x["key"] == "CODEX_MAX_RUNS_PER_DAY")
        settings_store.update(item["key"], 3, "admin", item["revision"])
        with self.assertRaises(ValueError):
            settings_store.update(item["key"], 4, "admin", item["revision"])
        self.assertEqual(settings_store.get(item["key"]), 3)
        self.assertEqual(settings_store.audit_events()[0]["key"], item["key"])

    def test_secrets_are_not_in_db(self):
        settings_store.initialize()
        self.assertNotIn(b"ORACLE_PASSWORD", self.path.read_bytes())
        self.assertNotIn(b"ADMIN_CF_AUD", self.path.read_bytes())

if __name__ == "__main__":
    unittest.main()
