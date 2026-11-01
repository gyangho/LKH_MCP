"""P1 agent event isolation, lease matching, idempotent cursor and limits."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_bridge as bridge
import codex_events as events


class CodexEventsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "events.sqlite"
        patcher = patch.object(bridge.settings_store, "_connect",
                               side_effect=lambda: sqlite3.connect(str(self.path)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.job = "a" * 32
        self.agent = "win-dev-01"
        self.lease = "a" * 64
        db = bridge._connect()
        db.execute("""INSERT INTO codex_agent_jobs(
            id,project,repository,branch,expected_sha,kind,instructions,
            state,actor,created_at,claimed_at,agent_id,lease_token_hash)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.job, "LKH", "gyangho/LKH_MCP", "refac", "a"*40,
             "verify", "", "running", "test", events.time.time(),
             int(events.time.time()), self.agent, hashlib.sha256(self.lease.encode()).hexdigest()))
        db.commit()
        db.close()

    def test_idempotent_events_and_cursor(self):
        payload = [{"seq": 1, "type": "started", "phase": "codex"},
                   {"seq": 2, "type": "command_completed", "phase": "test"}]
        events.append(self.job, self.agent, self.lease, payload)
        events.append(self.job, self.agent, self.lease, payload)
        result = events.read(self.job)
        self.assertEqual([e["seq"] for e in result["events"]], [1, 2])
        self.assertEqual(result["cursor"], 2)
        self.assertEqual(events.read(self.job, after=2)["events"], [])

    def test_wrong_lease_or_finished_job_denied(self):
        with self.assertRaises(PermissionError):
            events.append(self.job, self.agent, "x"*60,
                          [{"seq": 1, "type": "started", "phase": "codex"}])
        db = sqlite3.connect(self.path)
        db.execute("UPDATE codex_agent_jobs SET state='completed' WHERE id=?", (self.job,))
        db.commit(); db.close()
        with self.assertRaises(PermissionError):
            events.append(self.job, self.agent, self.lease,
                          [{"seq": 1, "type": "started", "phase": "codex"}])

    def test_raw_output_and_unknown_metadata_rejected(self):
        for row in (
            {"seq": 1, "type": "started", "phase": "codex", "command": "cat secret"},
            {"seq": 1, "type": "command", "phase": "codex"},
            {"seq": 1, "type": "started", "phase": "secret"},
            {"seq": True, "type": "started", "phase": "codex"},
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                events.append(self.job, self.agent, self.lease, [row])


if __name__ == "__main__":
    unittest.main()
