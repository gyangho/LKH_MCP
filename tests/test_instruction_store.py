"""Phase 4-6 draft/publish/rollback contracts and precedence."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import instruction_store as store


class InstructionsTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        db_path = str(Path(t.name) / "instructions.sqlite")
        p = patch.object(store.settings_store, "_connect",
                         side_effect=lambda: sqlite3.connect(db_path))
        p.start()
        self.addCleanup(p.stop)

    def test_draft_is_invisible_until_publish(self):
        result = store.create("policy", "global", "", "Global rule", "admin")
        self.assertEqual(store.list_entries()["instructions"], [])
        self.assertFalse(store.resolve("policy")["found"])
        with self.assertRaises(ValueError):
            store.get_entry(result["id"])
        published = store.publish(result["id"], 1, "admin")
        self.assertEqual(published["published_revision"], 1)
        self.assertEqual(store.resolve("policy")["body"], "Global rule")

    def test_optimistic_version_and_rollback(self):
        ident = store.create("policy", "global", "", "v1", "admin")["id"]
        store.publish(ident, 1, "admin")
        self.assertEqual(store.save(ident, "v2", 1, "admin")["revision"], 2)
        self.assertEqual(store.resolve("policy")["body"], "v1")
        with self.assertRaises(ValueError):
            store.save(ident, "stale", 1, "admin")
        store.publish(ident, 2, "admin")
        self.assertEqual(store.resolve("policy")["body"], "v2")
        store.rollback(ident, 1, 2, "admin")
        self.assertEqual(store.resolve("policy")["body"], "v1")
        self.assertEqual(len(store.history(ident)["versions"]), 2)

    def test_scope_precedence(self):
        for scope, key, body in (
            ("global", "", "global"), ("project", "ITAM", "project"),
            ("agent", "win-agent", "agent"), ("tool", "oracle_select_dual", "tool"),
        ):
            ident = store.create("policy", scope, key, body, "admin")["id"]
            store.publish(ident, 1, "admin")
        self.assertEqual(store.resolve("policy", project="ITAM", agent="win-agent",
                                       tool="oracle_select_dual")["body"], "tool")
        self.assertEqual(store.resolve("policy", project="ITAM")["body"], "project")
        self.assertEqual(store.resolve("policy", project="unknown")["body"], "global")

    def test_secret_and_duplicate_rejection(self):
        with self.assertRaises(ValueError):
            store.create("policy", "global", "", "password=topsecret123", "admin")
        store.create("policy", "global", "", "safe", "admin")
        with self.assertRaises(sqlite3.IntegrityError):
            store.create("policy", "global", "", "duplicate", "admin")


if __name__ == "__main__":
    unittest.main()
