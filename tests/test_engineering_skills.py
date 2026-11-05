"""Central skill registry, queue injection, and Windows prompt contract."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import engineering_skills as skills
import codex_bridge as bridge


class SkillFixtures(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / ".lkh-pinned-revision").write_text(skills.REVISION, encoding="ascii")
        (self.root / "LICENSE").write_text("MIT", encoding="utf-8")
        plugin = self.root / ".claude-plugin"
        plugin.mkdir()
        needed = {n for group in skills.WORKFLOWS.values() for n in group}
        needed.update(n for group in skills.AGENT_SKILLS.values() for n in group)
        registrations = []
        for name in sorted(needed):
            folder = self.root / "skills" / "engineering" / name
            folder.mkdir(parents=True)
            (folder / "SKILL.md").write_text("# " + name + "\nRun the procedure.", encoding="utf-8")
            registrations.append("./skills/engineering/" + name)
            if name == "tdd":
                (folder / "tests.md").write_text("Test visible behavior.", encoding="utf-8")
                (folder / "mocking.md").write_text("Use few mocks.", encoding="utf-8")
        (plugin / "plugin.json").write_text(json.dumps({"skills": registrations}), encoding="utf-8")
        p = patch.dict(os.environ, {"LKH_ENGINEERING_SKILLS_ROOT": str(self.root)})
        p.start(); self.addCleanup(p.stop)

    def _queue_connection(self, db):
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE IF NOT EXISTS approved_repositories (
            alias TEXT PRIMARY KEY, agent_id TEXT NOT NULL, local_path TEXT NOT NULL)""")
        conn.execute(
            "INSERT OR REPLACE INTO approved_repositories(alias,agent_id,local_path) VALUES(?,?,?)",
            ("ITAM", "", ""))
        conn.commit()
        return conn

    def test_catalog_get_workflow_and_mandatory_policy(self):
        self.assertGreater(len(skills.catalog()["skills"]), 5)
        self.assertEqual(skills.workflow("bugfix")["steps"],
                         ["diagnosing-bugs", "tdd", "code-review"])
        self.assertEqual(skills.workflow("verify")["steps"], ["tdd"])
        self.assertIn("Never commit or push", skills.skill_get("tdd")["priority_policy"])
        guidance = skills.agent_guidance("fix")
        self.assertIn("=== SKILL diagnosing-bugs ===", guidance)
        self.assertIn("=== SKILL code-review ===", guidance)
        self.assertIn("Use few mocks.", guidance)
        self.assertIn("temporary worktree", guidance)

    def test_feature_delivery_phases_have_explicit_evidence_gates(self):
        plan = skills.workflow("feature")
        self.assertEqual(plan["revision"], skills.REVISION)
        self.assertEqual(plan["steps"],
                         ["domain-modeling", "to-spec", "to-tickets",
                          "implement-spec", "code-review"])
        self.assertEqual([p["phase"] for p in plan["phases"]],
                         ["discover", "specify", "implement", "review", "verify"])
        self.assertTrue(all(p["gate"] for p in plan["phases"]))
        self.assertEqual(set(plan["completion_gates"]), {"code", "integration", "tests", "production"})
        self.assertEqual(skills.workflow("feature-small")["steps"],
                         ["domain-modeling", "tdd", "implement", "code-review"])
        self.assertIn("diagnosing-bugs", skills.workflow("bugfix")["steps"])
        self.assertNotIn("implement-spec", skills.workflow("verify")["steps"])
        self.assertRaises(ValueError, skills.workflow, "nonexistent")

    def test_v2_contract_requires_complete_agent_evidence(self):
        from windows_agent import agent
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        guidance = skills.agent_guidance("verify")
        contract = agent._engineering_contract(guidance)
        self.assertEqual(contract["version"], 2)
        self.assertEqual(contract["skills"][0]["name"], "tdd")
        self.assertEqual(len(contract["skills"][0]["sha256"]), 64)

        def fake_worktree(repo, sha, temp):
            temp.mkdir(parents=True)

        def run_response(payload):
            with patch.object(agent, "_make_worktree", side_effect=fake_worktree), \
                 patch.object(agent, "_remove_worktree"), \
                 patch.object(agent, "_codex", return_value=json.dumps(payload)):
                return agent.codex_task(root, "a"*40, "verify", "Run actual tests",
                                        workflow_guidance=guidance)

        base = {"passed": True, "status": "completed", "summary": "ok",
                "commands": ["python -m unittest"], "failures": [],
                "tests_executed": 1, "tests_failed": 0, "tests_skipped": 0}
        passed, report = run_response(base)
        self.assertFalse(passed)
        self.assertEqual(json.loads(report)["status"], "incomplete")
        good = dict(base, engineering_evidence={
            "revision": skills.REVISION, "applied_skills": ["tdd"],
            "skipped_skills": [],
            "checks": [{"criterion": "Regression behavior",
                        "result": "pass", "evidence": "1 test passed"}],
        })
        passed, report = run_response(good)
        self.assertTrue(passed)
        self.assertEqual(json.loads(report)["engineering_evidence_status"], "agent_reported")
        wrong = dict(good, engineering_evidence=dict(good["engineering_evidence"], revision="0"*40))
        self.assertFalse(run_response(wrong)[0])
        blocked = dict(good, engineering_evidence=dict(good["engineering_evidence"],
            checks=[{"criterion": "Integration", "result": "blocked", "evidence": "No test host"}]))
        self.assertFalse(run_response(blocked)[0])
        with self.assertRaises(ValueError):
            agent.codex_task(root, "a"*40, "diagnose", "No action",
                             workflow_guidance=guidance)

    def test_reference_restricts_paths_and_symlinks(self):
        self.assertIn("Test visible behavior.", skills.skill_reference("tdd", "tests.md")["content"])
        for name in ("../LICENSE", "x/../../LICENSE", "/etc/passwd",
                     "https://bad", "nested\\file.md", "tdd.md/.."):
            with self.subTest(name=name), self.assertRaises(ValueError):
                skills.skill_reference("tdd", name)
        outside = self.root / "secrets.md"
        outside.write_text("secret", encoding="utf-8")
        link = self.root / "skills" / "engineering" / "tdd" / "link.md"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not permitted on test host")
        with self.assertRaises(ValueError):
            skills.skill_reference("tdd", "link.md")

    def test_bad_manifest_marker_and_unknown_skill(self):
        with self.assertRaises(ValueError):
            skills.skill_get("missing")
        marker = self.root / ".lkh-pinned-revision"
        marker.write_text("invalid", encoding="ascii")
        with self.assertRaises(RuntimeError):
            skills.catalog()
        marker.write_text(skills.REVISION, encoding="ascii")
        manifest = self.root / ".claude-plugin" / "plugin.json"
        manifest.write_text(json.dumps({"skills": ["./../bad"]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            skills.catalog()

    def test_mcp_tools_are_registered_and_read_only(self):
        class FakeMCP:
            def __init__(self):
                self.tools = {}
            def tool(self):
                def wrapper(fn):
                    self.tools[fn.__name__] = fn
                    return fn
                return wrapper
        mcp = FakeMCP()
        skills.register_engineering_skills(mcp)
        self.assertEqual(len(mcp.tools), 4)
        self.assertTrue(mcp.tools["engineering_skills_list"]()["skills"])
        self.assertEqual(mcp.tools["engineering_skill_get"]("tdd")["name"], "tdd")

    def test_queue_claim_injects_pinned_guidance(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db = Path(folder.name) / "queue.sqlite"
        patches = [
            patch.object(bridge, "_allowed", return_value={"ITAM": "gyangho/ITAM"}),
            patch.object(bridge.settings_store, "_connect", side_effect=lambda: self._queue_connection(db)),
            patch.object(bridge.settings_store, "get", side_effect=lambda k:
                         {"CODEX_AGENT_ENABLED": True, "CODEX_MAX_RUNS_PER_DAY": 20}[k]),
        ]
        for p in patches:
            p.start(); self.addCleanup(p.stop)
        job = bridge.enqueue("ITAM", "main", "a" * 40, instructions="Run tests")
        result = bridge.claim("win-test", ["ITAM"])
        self.assertIn("=== SKILL tdd ===", result["job"]["engineering_guidance"])
        self.assertEqual(result["job"]["id"], job["id"])

    def test_missing_skills_does_not_consume_or_lease_job(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db = Path(folder.name) / "queue.sqlite"
        for p in [
            patch.object(bridge, "_allowed", return_value={"ITAM": "gyangho/ITAM"}),
            patch.object(bridge.settings_store, "_connect", side_effect=lambda: self._queue_connection(db)),
            patch.object(bridge.settings_store, "get", side_effect=lambda k:
                         {"CODEX_AGENT_ENABLED": True, "CODEX_MAX_RUNS_PER_DAY": 20}[k]),
        ]:
            p.start(); self.addCleanup(p.stop)
        job = bridge.enqueue("ITAM", "main", "a" * 40)
        with patch.object(skills, "agent_guidance", side_effect=RuntimeError("unavailable")):
            result = bridge.claim("win-test", ["ITAM"])
        self.assertIsNone(result["job"])
        self.assertEqual(result["reason"], "engineering_skills_unavailable")
        self.assertNotIn("lease", result)
        self.assertEqual(bridge.get_task(job["id"])["state"], "queued")

    def test_windows_agent_prompt_uses_central_skill(self):
        from windows_agent import agent
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        seen = []
        def fake_worktree(repo, sha, temp):
            temp.mkdir(parents=True)
        def fake_codex(repo, prompt, output, child_env=None):
            seen.append(prompt)
            return json.dumps({"passed": True, "summary": "ok",
                               "commands": [], "failures": []})
        with patch.object(agent, "_make_worktree", side_effect=fake_worktree), \
             patch.object(agent, "_remove_worktree"), \
             patch.object(agent, "_codex", side_effect=fake_codex):
            passed, _ = agent.codex_task(root, "a"*40, "verify", "Run tests",
                                        workflow_guidance="=== SKILL tdd ===\nFOLLOW ME")
        self.assertTrue(passed)
        self.assertIn("FOLLOW ME", seen[0])
        self.assertIn("Never commit", seen[0])
        self.assertLess(seen[0].index("Never commit"), seen[0].index("FOLLOW ME"))


if __name__ == "__main__":
    unittest.main()
