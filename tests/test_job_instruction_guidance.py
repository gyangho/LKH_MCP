"""Queue claims carry the published instruction snapshot without extra DB writers."""
import json
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import codex_bridge as bridge
import instruction_store as instructions


class JobInstructionGuidanceTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db = Path(folder.name) / "queue.sqlite"
        with closing(self.connect()) as db:
            db.execute("CREATE TABLE approved_repositories(alias TEXT PRIMARY KEY, agent_id TEXT, local_path TEXT)")
            db.execute("INSERT INTO approved_repositories VALUES('ITAM','win-test','C:/ITAM')")
        for p in (
            patch.object(bridge.settings_store, "_connect", side_effect=self.connect),
            patch.object(bridge.settings_store, "get", side_effect=lambda key:
                         {"CODEX_AGENT_ENABLED": True, "CODEX_MAX_RUNS_PER_DAY": 20}[key]),
            patch.object(bridge, "_allowed", return_value={"ITAM": "gyangho/ITAM"}),
            patch("engineering_skills.agent_guidance", return_value="Pinned engineering procedure"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def connect(self):
        return sqlite3.connect(self.db, timeout=0.1, isolation_level=None)

    def enqueue(self, kind="verify"):
        job = bridge.enqueue("ITAM", "main", "a" * 40, kind,
                             instructions="Diagnose and fix failing tests")
        if kind == "fix":
            bridge.decide(job["id"], "approve", "admin")
        return job

    def publish(self, name, scope="global", key="", body="Published procedure"):
        entry = instructions.create(name, scope, key, body, "admin")
        instructions.publish(entry["id"], 1, "admin")
        return entry

    def test_all_development_jobs_include_published_bodies_and_revisions(self):
        self.publish("lkh-mcp-usage", body="Use central engineering skills")
        gradle = self.publish("windows-gradle-verification", body="Use isolated Gradle home")
        instructions.save(gradle["id"], "Draft text must never be sent", 1, "admin")
        for kind in ("verify", "diagnose", "fix"):
            with self.subTest(kind=kind):
                job = self.enqueue(kind)
                result = bridge.claim("win-test", ["ITAM"])
                guidance = result["job"]["engineering_guidance"]
                self.assertIn("Use central engineering skills", guidance)
                self.assertIn("Use isolated Gradle home", guidance)
                self.assertIn('"revision": 1', guidance)
                self.assertNotIn("Draft text", guidance)
                bridge.complete(job["id"], result["lease"], "win-test", True, "Complete")

    def test_scope_precedence_uses_job_project_agent_and_enqueue_tool(self):
        name = "lkh-mcp-usage"
        self.publish(name, body="global text")
        self.publish(name, "project", "ITAM", "project text")
        self.publish(name, "agent", "win-test", "agent text")
        self.publish(name, "tool", "codex_enqueue", "tool text")
        self.enqueue()
        guidance = bridge.claim("win-test", ["ITAM"])["job"]["engineering_guidance"]
        self.assertIn("tool text", guidance)
        self.assertNotIn("agent text", guidance)
        self.assertIn('"scope": "tool"', guidance)
        self.assertIn('"scope_key": "codex_enqueue"', guidance)

    def test_fresh_queue_without_instruction_tables_reports_missing_optional_documents(self):
        self.enqueue()
        result = bridge.claim("win-test", ["ITAM"])
        self.assertIsNotNone(result["job"])
        guidance = result["job"]["engineering_guidance"]
        self.assertIn("lkh-mcp-usage", guidance)
        self.assertIn("windows-gradle-verification", guidance)
        self.assertIn('"found": false', guidance)
        with closing(self.connect()) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='instruction_entries'").fetchone())

    def test_lookup_error_does_not_lease_or_consume_job(self):
        job = self.enqueue()
        with patch.object(instructions, "resolve", side_effect=sqlite3.OperationalError("private detail")):
            result = bridge.claim("win-test", ["ITAM"])
        self.assertIsNone(result["job"])
        self.assertEqual(result["reason"], "engineering_instructions_unavailable")
        self.assertNotIn("private detail", json.dumps(result))
        self.assertNotIn("lease", result)
        self.assertEqual(bridge.get_task(job["id"])["state"], "queued")
        self.assertIsNone(bridge.get_task(job["id"])["claimed_at"])

    def test_combined_guidance_limit_preserves_queued_job(self):
        self.publish("lkh-mcp-usage")
        job = self.enqueue()
        with patch("engineering_skills.agent_guidance", return_value="x" * 49999):
            result = bridge.claim("win-test", ["ITAM"])
        self.assertIsNone(result["job"])
        self.assertEqual(result["reason"], "engineering_instructions_unavailable")
        self.assertEqual(bridge.get_task(job["id"])["state"], "queued")

    def test_incomplete_instruction_schema_is_not_treated_as_missing_documents(self):
        with closing(self.connect()) as db:
            db.execute("CREATE TABLE instruction_entries(id TEXT)")
        job = self.enqueue()
        result = bridge.claim("win-test", ["ITAM"])
        self.assertIsNone(result["job"])
        self.assertEqual(result["reason"], "engineering_instructions_unavailable")
        self.assertEqual(bridge.get_task(job["id"])["state"], "queued")

    def test_revoked_override_falls_back_to_published_project_document(self):
        self.publish("lkh-mcp-usage", "project", "ITAM", "Published project text")
        override = self.publish("lkh-mcp-usage", "agent", "win-test", "Revoked agent text")
        instructions.revoke(override["id"], 1, "admin")
        self.enqueue()
        guidance = bridge.claim("win-test", ["ITAM"])["job"]["engineering_guidance"]
        self.assertIn("Published project text", guidance)
        self.assertNotIn("Revoked agent text", guidance)


if __name__ == "__main__":
    unittest.main()
