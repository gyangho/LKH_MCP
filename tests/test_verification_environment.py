"""Real asset staging plus sandbox boundary and fail-closed Agent regressions."""
import json
import os
import subprocess
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verification_environment as verification
from windows_agent import agent


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "worktree"
        self.root.mkdir()
        self.backend = self.root / "backend"
        wrapper = self.backend / "gradle/wrapper"
        wrapper.mkdir(parents=True)
        (wrapper / "gradle-wrapper.properties").write_text(
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.5.1-bin.zip\n")
        self.distribution = self.base / "approved/gradle-9.5.1"
        (self.distribution / "lib/agents").mkdir(parents=True)
        for file in ("lib/gradle-gradle-cli-main-9.5.1.jar",
                     "lib/agents/gradle-instrumentation-agent-9.5.1.jar"):
            (self.distribution / file).write_bytes(b"fixture")
        self.cache = self.base / "approved/modules-2"
        (self.cache / "files-2.1").mkdir(parents=True)
        (self.cache / "files-2.1/dependency.jar").write_bytes(b"dependency")
        (self.cache / "modules-2.lock").write_text("do not copy")
        (self.cache / "gc.properties").write_text("do not copy")
        self.project = self.root / "frontend"
        self.project.mkdir()
        self.snapshot = self.base / "approved/frontend"
        (self.snapshot / "node_modules/tool").mkdir(parents=True)
        self.packages = {"node_modules/tool": {"version": "1.0", "integrity": "sha512-fixture"}}
        for path in (self.project, self.snapshot):
            (path / "package.json").write_text('{"devDependencies":{"tool":"1.0"}}')
            (path / "package-lock.json").write_text(json.dumps(
                {"lockfileVersion": 3, "packages": {"": {}, **self.packages}}))
        (self.snapshot / "node_modules/.package-lock.json").write_text(
            json.dumps({"lockfileVersion": 3, "packages": self.packages}))
        (self.snapshot / "node_modules/tool/index.js").write_text("module.exports = 1;")
        self.java = self.base / "approved/jdk/bin/java.exe"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"fixture")
        self.node = self.base / "approved/node/node.exe"
        self.node.parent.mkdir()
        self.node.write_bytes(b"fixture")
        self.profile = {
            "repository": "example/project", "path": str(self.base / "canonical"),
            "gradle": {"project_dir": "backend", "distribution": str(self.distribution),
                       "dependency_cache": str(self.cache), "java_executable": str(self.java)},
            "frontend": {"project_dir": "frontend", "snapshot": str(self.snapshot),
                         "node_executable": str(self.node)},
        }
        self.runner = patch.object(verification.subprocess, "run", return_value=
                                   subprocess.CompletedProcess([], 0, "preflight passed"))
        self.run = self.runner.start()
        self.addCleanup(self.runner.stop)

    def prepare(self):
        return verification.prepare(self.root, self.profile, {"PATH": "trusted-tools"}, "codex.exe")

    def test_stages_assets_and_preflights_only_inside_managed_sandbox(self):
        verification.validate_profiles({"project": self.profile})
        manifest, env = self.prepare()
        home = self.root / ".lkh-verification/gradle-home"
        self.assertEqual((home / "caches/modules-2/files-2.1/dependency.jar").read_bytes(), b"dependency")
        self.assertFalse((home / "caches/modules-2/modules-2.lock").exists())
        self.assertFalse((home / "caches/modules-2/gc.properties").exists())
        self.assertEqual((self.cache / "modules-2.lock").read_text(), "do not copy")
        self.assertTrue((self.project / "node_modules/tool/index.js").is_file())
        self.assertFalse((self.project / "node_modules").is_symlink())
        self.assertEqual(env["GRADLE_USER_HOME"], str(home))
        self.assertTrue(Path(env["NPM_CONFIG_USERCONFIG"]).is_relative_to(self.root))
        self.assertEqual(Path(env["NPM_CONFIG_USERCONFIG"]).read_text(), "")
        self.assertEqual(env["NPM_CONFIG_OFFLINE"], "true")
        self.assertTrue(Path(env["TEMP"]).is_relative_to(self.root))
        self.assertEqual(manifest["tests_executed"], 0)
        self.assertEqual(manifest["gradle"]["preflight"], "passed")
        self.assertEqual(manifest["frontend"]["preflight"], "passed")
        self.assertEqual(self.run.call_count, 2)
        for call in self.run.call_args_list:
            args = call.args[0]
            self.assertEqual(args[:5], ["codex.exe", "sandbox", "--include-managed-config",
                                      "--permission-profile", ":workspace"])
            self.assertEqual(call.kwargs["cwd"], self.root)
            self.assertFalse(call.kwargs["shell"])
            self.assertNotIn("danger-full-access", args)
            self.assertFalse(any("network_access" in x for x in args))
        gradle = self.run.call_args_list[0].args[0]
        self.assertEqual(gradle[-1], "help")
        self.assertIn("--offline", gradle)
        self.assertIn("--no-daemon", gradle)

    def test_loopback_failure_is_sanitized_and_does_not_run_second_preflight(self):
        self.run.return_value = subprocess.CompletedProcess([], 1,
            "private-token=SECRET java.net.SocketException: Permission denied: getsockopt")
        with self.assertRaises(verification.PreparationError) as caught:
            self.prepare()
        self.assertIn("VERIFICATION_LOOPBACK_DENIED", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))
        self.assertEqual(self.run.call_count, 1)

    def test_missing_offline_dependencies_are_reported_without_output(self):
        self.run.return_value = subprocess.CompletedProcess([], 1, "No cached version of private-library")
        with self.assertRaisesRegex(verification.PreparationError, "OFFLINE_DEPENDENCY_MISSING"):
            self.prepare()

    def test_preflight_timeout_is_reported(self):
        self.run.side_effect = subprocess.TimeoutExpired("private command", 180)
        with self.assertRaisesRegex(verification.PreparationError, "PREFLIGHT_TIMEOUT"):
            self.prepare()

    def test_snapshot_lock_mismatch_stops_before_any_project_execution(self):
        (self.snapshot / "package-lock.json").write_text("{}")
        with self.assertRaisesRegex(verification.PreparationError, "FRONTEND_LOCK_MISMATCH"):
            self.prepare()
        self.run.assert_not_called()

    def test_installed_package_mismatch_is_rejected(self):
        (self.snapshot / "node_modules/.package-lock.json").write_text(json.dumps(
            {"packages": {"node_modules/tool": {"version": "2.0"}}}))
        with self.assertRaisesRegex(verification.PreparationError, "FRONTEND_LOCK_MISMATCH"):
            self.prepare()
        self.run.assert_not_called()

    def test_optional_absent_package_is_allowed(self):
        for path in (self.project, self.snapshot):
            lock = json.loads((path / "package-lock.json").read_text())
            lock["packages"]["node_modules/optional-platform"] = {"version": "1", "optional": True}
            (path / "package-lock.json").write_text(json.dumps(lock))
        self.prepare()
        self.assertEqual(self.run.call_count, 2)

    def test_wrapper_version_mismatch_is_rejected(self):
        (self.backend / "gradle/wrapper/gradle-wrapper.properties").write_text(
            "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.6.0-bin.zip")
        with self.assertRaises(verification.PreparationError):
            self.prepare()
        self.run.assert_not_called()

    def test_missing_distribution_has_actionable_sanitized_code(self):
        self.profile["gradle"]["distribution"] = str(self.base / "private-location-do-not-log")
        with self.assertRaisesRegex(verification.PreparationError, "GRADLE_DISTRIBUTION_UNAVAILABLE") as caught:
            self.prepare()
        self.assertNotIn("private-location", str(caught.exception))
        self.run.assert_not_called()

    def test_reserved_staging_collision_does_not_overwrite_repository(self):
        staging = self.root / ".lkh-verification"
        staging.mkdir()
        (staging / "keep.txt").write_text("protected")
        with self.assertRaises(verification.PreparationError):
            self.prepare()
        self.assertEqual((staging / "keep.txt").read_text(), "protected")
        self.run.assert_not_called()

    def test_rejects_symlink_in_approved_assets(self):
        try:
            (self.cache / "linked-secret").symlink_to(self.java)
        except OSError:
            self.skipTest("Host does not permit symlink creation")
        with self.assertRaisesRegex(verification.PreparationError, "LINK_OR_SPECIAL_FILE"):
            self.prepare()
        self.run.assert_not_called()

    def test_reparse_point_is_rejected_even_without_symlink_privilege(self):
        info = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=info), \
                self.assertRaisesRegex(verification.PreparationError, "LINK_OR_SPECIAL_FILE"):
            verification._plain(self.cache)

    def test_batch_launcher_metacharacters_do_not_reach_subprocess(self):
        with self.assertRaisesRegex(verification.PreparationError, "UNSAFE_LAUNCH_ARGUMENT"):
            verification._sandbox(["java.exe", "path&injected"], self.root, {}, "codex.cmd")
        self.run.assert_not_called()

    def test_rejects_source_containing_destination(self):
        with self.assertRaisesRegex(verification.PreparationError, "SOURCE_OVERLAPS_WORKSPACE"):
            verification._Copier().copy(self.base, self.root / "copy")
        self.run.assert_not_called()

    def test_cache_cannot_include_user_configuration_or_credentials(self):
        (self.cache / ".npmrc").write_text("synthetic-private-value")
        with self.assertRaisesRegex(verification.PreparationError, "CACHE_LAYOUT_INVALID"):
            self.prepare()
        self.assertFalse((self.root / ".lkh-verification/gradle-home/caches/modules-2/.npmrc").exists())
        self.run.assert_not_called()

    def test_profile_cannot_inject_policy_or_escape_project(self):
        for directory in ("../outside", "C:/outside", "//host/share", ".git"):
            with self.subTest(directory=directory):
                self.profile["gradle"]["project_dir"] = directory
                with self.assertRaises(verification.PreparationError):
                    verification.validate_profiles({"project": self.profile})
        self.profile["gradle"]["project_dir"] = "backend"
        self.profile["network_access"] = True
        with self.assertRaises(verification.PreparationError):
            verification.validate_profiles({"project": self.profile})

    def test_profile_binding_must_match_current_repository_and_path(self):
        config = {"verification_environments": {"project": self.profile}}
        for repo, root in (("attacker/project", self.base / "canonical"),
                           ("example/project", self.root)):
            with self.subTest(repo=repo, root=root), self.assertRaisesRegex(
                    verification.PreparationError, "PROFILE_BINDING_MISMATCH"):
                verification.select_profile(config, "project", repo, root)

    def test_process_rejects_changed_binding_before_fetch_or_worktree_creation(self):
        config = {"verification_environments": {"project": self.profile},
                  "projects": {"project": {"repository": "example/project", "path": str(self.root)}}}
        job = {"project": "project", "repository": "example/project", "branch": "main",
               "expected_sha": "a" * 40, "kind": "verify"}
        with patch.object(agent, "safe_pull") as pull, patch.object(agent, "codex_task") as task:
            ok, report, error, _ = agent.process(job, config)
        self.assertFalse(ok)
        self.assertEqual(json.loads(report)["status"], "environment_blocked")
        self.assertIn("PROFILE_BINDING_MISMATCH", error)
        pull.assert_not_called()
        task.assert_not_called()

    def test_process_uses_local_profile_and_ignores_job_asset_paths(self):
        self.profile["path"] = str(self.root)
        config = {"verification_environments": {"project": self.profile},
                  "projects": {"project": {"repository": "example/project", "path": str(self.root)}}}
        job = {"project": "project", "repository": "example/project", "branch": "main",
               "expected_sha": "a" * 40, "kind": "verify", "instructions": "run tests",
               "verification_environments": {"project": {"path": "attacker-path"}}}
        with patch.object(agent, "safe_pull", return_value="a" * 40), \
                patch.object(agent, "git", return_value="a" * 40), \
                patch.object(agent, "codex_task", return_value=(True, "passed")) as task:
            self.assertTrue(agent.process(job, config)[0])
        self.assertEqual(task.call_args.kwargs["preparation"], self.profile)


class AgentPreparationTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch.object(agent, "_make_worktree"), patch.object(agent, "_remove_worktree"),
                        patch.object(agent.shutil, "which", return_value="codex.exe"),
                        patch.object(agent, "prepare"), patch.object(agent, "_codex_jsonl"),
                        patch.object(agent, "_codex"), patch.object(agent, "git", return_value="a" * 40)]
        self.make, self.remove, self.which, self.prepare, self.jsonl, self.codex, self.git = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.profile = {"fixture": True}

    def test_preparation_failure_blocks_model_and_reports_zero_tests(self):
        self.prepare.side_effect = verification.PreparationError("VERIFICATION_LOOPBACK_DENIED")
        events = Mock()
        ok, report = agent.codex_task(Path("canonical"), "a" * 40, "verify", "run tests",
                                      events, preparation=self.profile)
        self.assertFalse(ok)
        data = json.loads(report)
        self.assertEqual(data["status"], "environment_blocked")
        self.assertEqual(data["tests_executed"], 0)
        self.jsonl.assert_not_called()
        self.codex.assert_not_called()
        self.remove.assert_called_once()
        self.assertEqual(events.call_args.args, ("error", "build"))

    def test_prepared_environment_is_passed_to_model_without_changing_sandbox(self):
        manifest = {"tests_executed": 0, "gradle": {"preflight": "passed", "command": ["approved-java"]}}
        self.prepare.return_value = manifest, {"PATH": "sanitized", "GRADLE_USER_HOME": "worktree-cache"}
        self.jsonl.return_value = json.dumps({"passed": True, "summary": "tests passed"})
        ok, _ = agent.codex_task(Path("canonical"), "a" * 40, "verify", "run tests",
                                 Mock(), preparation=self.profile)
        self.assertTrue(ok)
        prompt = self.jsonl.call_args.args[1]
        self.assertIn("a" * 40, prompt)
        self.assertIn("approved-java", prompt)
        self.assertEqual(self.jsonl.call_args.kwargs["child_env"]["GRADLE_USER_HOME"], "worktree-cache")
        self.remove.assert_called_once()

    def test_unconfigured_project_retains_existing_verification_flow(self):
        self.codex.return_value = '{"passed":true,"summary":"legacy tests"}'
        ok, _ = agent.codex_task(Path("canonical"), "a" * 40, "verify", "run tests")
        self.assertTrue(ok)
        self.prepare.assert_not_called()
        self.codex.assert_called_once()

    def test_preflight_tracked_changes_block_model_execution(self):
        self.prepare.return_value = {"tests_executed": 0}, {"PATH": "sanitized"}
        self.git.side_effect = RuntimeError("git exited with code 1")
        ok, report = agent.codex_task(Path("canonical"), "a" * 40, "verify", "run tests",
                                      Mock(), preparation=self.profile)
        self.assertFalse(ok)
        self.assertIn("VERIFICATION_PREFLIGHT_GIT_STATE_REJECTED", report)
        self.jsonl.assert_not_called()
        self.codex.assert_not_called()
        self.remove.assert_called_once()


class PreparedExecutionTests(unittest.TestCase):
    def test_jsonl_launcher_preserves_workspace_sandbox_and_prepared_environment(self):
        proc = Mock()
        proc.stdout = iter(())
        proc.wait.return_value = 0
        proc.poll.return_value = 0
        environment = {"PATH": "sanitized", "GRADLE_USER_HOME": "worktree-cache"}
        with patch.object(agent.shutil, "which", return_value="codex.exe"), \
                patch.object(agent.subprocess, "Popen", return_value=proc) as launch:
            agent._codex_jsonl(Path.cwd(), "prompt", Path("absent-result"), Mock(), child_env=environment)
        args = launch.call_args.args[0]
        self.assertEqual(args[args.index("--sandbox") + 1], "workspace-write")
        self.assertIs(launch.call_args.kwargs["env"], environment)
        self.assertFalse(launch.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
