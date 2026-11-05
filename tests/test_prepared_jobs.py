"""All development jobs receive the same approved local preparation flow."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verification_environment import PreparationError
from windows_agent import agent


class PreparedJobsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.profile = {
            "repository": "example/project", "path": str(self.root),
            "gradle": {"project_dir": "backend", "distribution": str(self.root / "gradle"),
                       "dependency_cache": str(self.root / "modules-2"),
                       "java_executable": str(self.root / "java.exe")},
        }
        self.config = {"projects": {"project": {"repository": "example/project", "path": str(self.root)}},
                       "verification_environments": {"project": self.profile}}

    def job(self, kind):
        return {"project": "project", "repository": "example/project", "branch": "main",
                "expected_sha": "a" * 40, "kind": kind, "instructions": "Run requested tests",
                "engineering_guidance": "Pinned engineering guidance"}

    def test_all_development_jobs_select_bound_local_profile(self):
        for kind in ("verify", "diagnose", "fix"):
            with self.subTest(kind=kind), \
                    patch.object(agent, "safe_pull", return_value="a" * 40), \
                    patch.object(agent, "git", return_value="a" * 40), \
                    patch.object(agent, "codex_task", return_value=(True, "done")) as task:
                self.assertTrue(agent.process(self.job(kind), self.config)[0])
                self.assertEqual(task.call_args.kwargs["preparation"], self.profile)

    def test_diagnose_and_fix_reject_mismatched_profile_before_git(self):
        self.profile["path"] = str(self.root / "different")
        for kind in ("diagnose", "fix"):
            with self.subTest(kind=kind), patch.object(agent, "safe_pull") as pull:
                ok, report, _, _ = agent.process(self.job(kind), self.config)
                self.assertFalse(ok)
                self.assertEqual(json.loads(report)["status"], "environment_blocked")
                pull.assert_not_called()

    def test_all_development_jobs_stop_before_model_when_preflight_fails(self):
        for kind in ("verify", "diagnose", "fix"):
            with self.subTest(kind=kind), patch.object(agent, "_make_worktree"), \
                    patch.object(agent, "_remove_worktree"), \
                    patch.object(agent.shutil, "which", return_value="codex.exe"), \
                    patch.object(agent, "prepare", side_effect=PreparationError("VERIFICATION_LOOPBACK_DENIED")), \
                    patch.object(agent, "_codex_jsonl") as model:
                ok, report = agent.codex_task(self.root, "a" * 40, kind, "Run tests", Mock(),
                                             preparation=self.profile, workflow_guidance="Pinned guidance")
                self.assertFalse(ok)
                self.assertEqual(json.loads(report)["tests_executed"], 0)
                model.assert_not_called()

    def test_prepared_diagnose_passes_command_manifest_and_environment_to_model(self):
        manifest = {"gradle": {"command": ["approved-java"]}, "tests_executed": 0}
        runtime = {"GRADLE_USER_HOME": "isolated-home"}
        with patch.object(agent, "_make_worktree"), patch.object(agent, "_remove_worktree"), \
                patch.object(agent.shutil, "which", return_value="codex.exe"), \
                patch.object(agent, "prepare", return_value=(manifest, runtime)), \
                patch.object(agent, "git", return_value="a" * 40), \
                patch.object(agent, "_codex", return_value='{"passed":true,"summary":"Diagnosis complete"}') as model:
            self.assertTrue(agent.codex_task(self.root, "a" * 40, "diagnose", "Investigate",
                                            preparation=self.profile, workflow_guidance="Pinned guidance")[0])
        self.assertIs(model.call_args.kwargs["child_env"], runtime)
        self.assertIn("approved-java", model.call_args.args[1])
        self.assertIn("tests_executed", model.call_args.args[1])

    def test_failure_status_cannot_report_success_and_unknown_test_counts_are_preserved(self):
        for status, count in (("environment_blocked", 0), ("compile_failed", 0),
                              ("test_failed", 4), ("incomplete", None)):
            with self.subTest(status=status), patch.object(agent, "_make_worktree"), \
                    patch.object(agent, "_remove_worktree"), \
                    patch.object(agent, "_codex", return_value=json.dumps(
                        {"passed": True, "summary": "not complete", "status": status,
                         "tests_executed": count})):
                ok, report = agent.codex_task(self.root, "a" * 40, "verify", "Run tests",
                                             workflow_guidance="Pinned guidance")
                self.assertFalse(ok)
                self.assertEqual(json.loads(report)["status"], status)
                self.assertEqual(json.loads(report)["tests_executed"], count)

    def test_legacy_result_does_not_invent_test_count(self):
        with patch.object(agent, "_make_worktree"), patch.object(agent, "_remove_worktree"), \
                patch.object(agent, "_codex", return_value='{"passed":true,"summary":"Done"}'):
            ok, report = agent.codex_task(self.root, "a" * 40, "verify", "Run tests",
                                         workflow_guidance="Pinned guidance")
        self.assertTrue(ok)
        self.assertNotIn("tests_executed", json.loads(report))

    def test_report_preserves_only_actual_nonnegative_integer_counts(self):
        for count in (True, -1, "5", 2.5):
            with self.subTest(invalid=count), patch.object(agent, "_make_worktree"), \
                    patch.object(agent, "_remove_worktree"), \
                    patch.object(agent, "_codex", return_value=json.dumps(
                        {"passed": True, "summary": "Done", "status": "completed",
                         "tests_executed": count, "tests_failed": count, "tests_skipped": count})):
                _, report = agent.codex_task(self.root, "a" * 40, "verify", "Run tests",
                                            workflow_guidance="Pinned guidance")
                self.assertNotIn("tests_executed", json.loads(report))
                self.assertNotIn("tests_failed", json.loads(report))
                self.assertNotIn("tests_skipped", json.loads(report))
        with patch.object(agent, "_make_worktree"), patch.object(agent, "_remove_worktree"), \
                patch.object(agent, "_codex", return_value=json.dumps(
                    {"passed": True, "summary": "Tests failed", "status": "completed",
                     "tests_executed": 8, "tests_failed": 2, "tests_skipped": 1})):
            ok, report = agent.codex_task(self.root, "a" * 40, "verify", "Run tests",
                                         workflow_guidance="Pinned guidance")
        self.assertFalse(ok)
        self.assertEqual(json.loads(report)["status"], "test_failed")
        self.assertEqual(json.loads(report)["tests_executed"], 8)
        self.assertEqual(json.loads(report)["tests_failed"], 2)
        self.assertEqual(json.loads(report)["tests_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
