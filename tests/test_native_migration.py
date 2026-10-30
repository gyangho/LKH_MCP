"""Destructive migration guards and WAL-consistent staging copy test."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from native_migration import copy_snapshot, inspect_database


class MigrationTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.original = self.root / "original.sqlite3"
        self.source_connection = sqlite3.connect(self.original)
        self.addCleanup(self.source_connection.close)
        self.source_connection.execute("PRAGMA journal_mode=WAL")
        self.source_connection.execute("CREATE TABLE critical_events (id INTEGER PRIMARY KEY, name TEXT)")
        self.source_connection.execute("INSERT INTO critical_events(name) VALUES ('keep')")
        self.source_connection.commit()

    def test_backup_api_includes_live_wal_and_preserves_source(self):
        before = inspect_database(self.original)
        dest = self.root / "staging.sqlite3"
        result = copy_snapshot(self.original, dest)
        self.assertEqual(result["integrity"], "ok")
        self.assertEqual(inspect_database(dest)["tables"], before["tables"])
        self.assertEqual(before["tables"]["critical_events"], 1)
        self.source_connection.execute("INSERT INTO critical_events(name) VALUES ('after')")
        self.source_connection.commit()
        self.assertEqual(inspect_database(dest)["tables"]["critical_events"], 1)
        self.assertEqual(inspect_database(self.original)["tables"]["critical_events"], 2)

    def test_never_overwrites_or_deletes_existing_data(self):
        dest = self.root / "existing.sqlite3"
        dest.write_bytes(b"KEEP")
        with self.assertRaises(FileExistsError):
            copy_snapshot(self.original, dest)
        self.assertEqual(dest.read_bytes(), b"KEEP")
        with self.assertRaises(ValueError):
            copy_snapshot(self.original, self.original)

    def test_requires_explicit_existing_destination_directory(self):
        with self.assertRaises(FileNotFoundError):
            copy_snapshot(self.original, self.root / "missing" / "copy.db")


if __name__ == "__main__":
    unittest.main()
