"""Phases 7/8 safe telemetry, retention, time buckets."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import operations_store as logs


class OperationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        dest = str(Path(temp.name) / "operations.sqlite")
        p = patch.object(logs.settings_store, "_connect",
                         side_effect=lambda: sqlite3.connect(dest))
        p.start()
        self.addCleanup(p.stop)

    def test_logs_and_metrics(self):
        logs.record("tool", "oracle_select_dual", "success", 10)
        logs.record("tool", "codex_enqueue", "error", 15)
        found = logs.read_events()
        self.assertEqual([e["name"] for e in found["events"]],
                         ["oracle_select_dual", "codex_enqueue"])
        self.assertEqual(logs.read_events(cursor=found["cursor"])["events"], [])
        self.assertEqual(len(found["events"][0]["trace_id"]), 32)
        buckets = logs.metrics(60)["buckets"]
        self.assertEqual(sum(b["requests"] for b in buckets), 2)
        self.assertEqual(sum(b["errors"] for b in buckets), 1)

    def test_secret_or_unbounded_content_refused(self):
        with self.assertRaises(ValueError):
            logs.record("tool", "Authorization: Bearer secret-token", "error")
        with self.assertRaises(ValueError):
            logs.record("tool", "test", "error", -1)
        with self.assertRaises(ValueError):
            logs.read_events(limit=5000)


if __name__ == "__main__":
    unittest.main()
