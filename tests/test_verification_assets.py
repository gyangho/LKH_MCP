"""Local registration and explicitly authorized sandbox refresh contracts."""
import json
import io
from contextlib import redirect_stderr
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import verification_assets as assets


class AssetRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "agent.json"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.profile = {"repository": "example/project", "path": str(self.repo),
                        "frontend": {"project_dir": "frontend", "snapshot": str(self.base / "old"),
                                     "node_executable": str(self.base / "node.exe")}}
        self.original = {"agent_id": "private-agent", "token": "DO-NOT-PRINT",
                         "projects": {"ITAM": {"repository": "example/project", "path": str(self.repo)}}}
        self.config.write_text(json.dumps(self.original), encoding="utf-8")

    def test_registration_preserves_private_fields_and_only_adds_profile(self):
        result = assets.register(self.config, "ITAM", self.profile)
        written = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(written["token"], "DO-NOT-PRINT")
        self.assertEqual(written["projects"], self.original["projects"])
        self.assertEqual(written["verification_environments"]["ITAM"], self.profile)
        self.assertEqual(result, {"status": "registered", "project": "ITAM"})
        self.assertNotIn("DO-NOT-PRINT", json.dumps(result))

    def test_completed_windows_replace_is_success_when_backup_cleanup_is_denied(self):
        kernel = Mock()
        kernel.ReplaceFileW.return_value = 1
        warning = io.StringIO()
        with patch.object(assets.ctypes, "WinDLL", return_value=kernel, create=True), \
                patch.object(Path, "unlink", side_effect=PermissionError("DO-NOT-PRINT")), \
                patch.object(assets.os, "replace") as rollback, redirect_stderr(warning):
            assets._windows_replace_config(self.base / "new.tmp", self.config)
        rollback.assert_not_called()
        self.assertEqual(warning.getvalue().strip(), "ASSETS_CONFIG_BACKUP_CLEANUP_PENDING")

    def test_registration_rejects_repository_binding_mismatch_without_writing(self):
        self.profile["repository"] = "attacker/project"
        with self.assertRaisesRegex(assets.AssetError, "BINDING_MISMATCH"):
            assets.register(self.config, "ITAM", self.profile)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), self.original)

    def test_explicit_bind_project_bootstraps_missing_managed_alias(self):
        self.original["projects"] = {}
        self.config.write_text(json.dumps(self.original), encoding="utf-8")
        assets.register(self.config, "ITAM", self.profile, bind_project=True)
        written = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(written["projects"]["ITAM"], {"repository": "example/project", "path": str(self.repo)})
        self.assertEqual(written["token"], "DO-NOT-PRINT")

    def test_explicit_bind_project_replaces_stale_alias_and_preserves_other_projects(self):
        self.original["projects"]["ITAM"] = {"repository": "old/project", "path": str(self.base / "stale")}
        self.original["projects"]["OTHER"] = {"repository": "example/other", "path": str(self.base / "other")}
        self.config.write_text(json.dumps(self.original), encoding="utf-8")
        assets.register(self.config, "ITAM", self.profile, bind_project=True)
        written = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(written["projects"]["ITAM"], {"repository": "example/project", "path": str(self.repo)})
        self.assertEqual(written["projects"]["OTHER"], self.original["projects"]["OTHER"])

    def test_missing_managed_alias_without_explicit_binding_does_not_change_config(self):
        self.original["projects"] = {}
        self.config.write_text(json.dumps(self.original), encoding="utf-8")
        before = self.config.read_bytes()
        with self.assertRaisesRegex(assets.AssetError, "BINDING_MISMATCH"):
            assets.register(self.config, "ITAM", self.profile)
        self.assertEqual(self.config.read_bytes(), before)

    def test_concurrent_config_edit_is_not_overwritten(self):
        before = self.config.read_bytes()
        self.config.write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(assets.AssetError, "CONFIG_CHANGED"):
            assets._write(self.config, self.original, before)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), {"changed": True})

    def test_windows_config_update_uses_acl_preserving_replace_without_weak_fallback(self):
        source = self.base / "new.tmp"
        source.write_text("new config")
        kernel = Mock()
        kernel.ReplaceFileW.return_value = 1
        with patch.object(assets.ctypes, "WinDLL", return_value=kernel, create=True), \
                patch.object(assets.os, "replace") as rename, patch.object(assets.os, "chmod") as chmod:
            assets._windows_replace_config(source, self.config)
        arguments = kernel.ReplaceFileW.call_args.args
        self.assertEqual(arguments[:2], (str(self.config), str(source)))
        self.assertEqual(arguments[3:], (0, None, None))
        rename.assert_not_called()
        chmod.assert_not_called()

    def test_refresh_requires_explicit_project_execution_acknowledgement(self):
        assets.register(self.config, "ITAM", self.profile)
        with patch.object(assets.subprocess, "run") as run:
            result = assets.refresh(self.config, "ITAM", "a" * 40, self.base / "new")
        self.assertEqual(result["status"], "planned")
        run.assert_not_called()
        self.assertFalse((self.base / "new").exists())

    def test_refresh_never_overwrites_existing_output(self):
        assets.register(self.config, "ITAM", self.profile)
        output = self.base / "new"
        output.mkdir()
        (output / "keep.txt").write_text("keep")
        with self.assertRaisesRegex(assets.AssetError, "OUTPUT_EXISTS"):
            assets.refresh(self.config, "ITAM", "a" * 40, output, allow_project_code=True)
        self.assertEqual((output / "keep.txt").read_text(), "keep")

    def test_sandbox_failure_keeps_old_config_and_sanitizes_output(self):
        assets.register(self.config, "ITAM", self.profile)
        before = self.config.read_bytes()
        with patch.object(assets, "_refresh", side_effect=OSError("token=PRIVATE")):
            with self.assertRaisesRegex(assets.AssetError, "REFRESH_FAILED") as raised:
                assets.refresh(self.config, "ITAM", "a" * 40, self.base / "new", allow_project_code=True,
                               codex="codex.exe")
        self.assertNotIn("PRIVATE", str(raised.exception))
        self.assertEqual(self.config.read_bytes(), before)

    def test_sandbox_has_managed_profile_and_never_security_overrides(self):
        with patch.object(assets.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "")) as run:
            assets._sandbox(["node.exe", "npm-cli.js", "ci"], self.repo, {}, "codex.exe")
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["codex.exe", "sandbox", "--include-managed-config", "--permission-profile", ":workspace"])
        self.assertNotIn("danger-full-access", command)
        self.assertNotIn("--network", command)
        self.assertFalse(run.call_args.kwargs["shell"])

    def test_loopback_failure_does_not_expose_project_output(self):
        result = subprocess.CompletedProcess([], 1, "token=PRIVATE Permission denied: getsockopt")
        with patch.object(assets.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(assets.AssetError, "ASSETS_LOOPBACK_DENIED") as raised:
                assets._sandbox(["java.exe", "compile"], self.repo, {}, "codex.exe")
        self.assertNotIn("PRIVATE", str(raised.exception))

    def test_refresh_environment_recovers_system_drive_without_passing_tokens(self):
        with patch.dict(assets.os.environ, {"SystemRoot": r"D:\Windows", "AGENT_TOKEN": "PRIVATE"}, clear=True), \
                patch.object(assets.sys, "platform", "win32"):
            env = assets._runtime(self.base)
        self.assertEqual(env["SystemDrive"], "D:")
        self.assertNotIn("AGENT_TOKEN", env)

    def _installed_node(self):
        node = self.base / "node/node.exe"
        node.parent.mkdir()
        node.write_bytes(b"fixture")
        npm = node.parent / "node_modules/npm/bin/npm-cli.js"
        npm.parent.mkdir(parents=True)
        npm.write_text("fixture")
        self.profile["frontend"]["node_executable"] = str(node)
        assets.register(self.config, "ITAM", self.profile)

    def test_successful_refresh_exports_lock_matched_assets_then_switches_config(self):
        self._installed_node()
        output = self.base / "new"
        packages = {"node_modules/tool": {"version": "1.0", "integrity": "sha512-fixture"}}
        def git(root, *args):
            if args[:2] == ("worktree", "add"):
                frontend = Path(args[-2]) / "frontend"
                frontend.mkdir(parents=True)
                (frontend / "package.json").write_text('{"dependencies":{"tool":"1.0"}}')
                (frontend / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}, **packages}}))
            if args[:2] == ("rev-parse", "HEAD"):
                return "a" * 40
            return ""
        def sandbox(command, root, env, codex):
            installed = root / "frontend/node_modules"
            (installed / "tool").mkdir(parents=True)
            (installed / "tool/index.js").write_text("module.exports=1")
            (installed / ".package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": packages}))
            self.assertEqual(command[-3:], ["ci", "--no-audit", "--no-fund"])
            self.assertEqual(Path(env["NPM_CONFIG_USERCONFIG"]).read_text(), "")
        with patch.object(assets, "_repository") as repo, patch.object(assets, "_git", side_effect=git), \
                patch.object(assets, "_sandbox", side_effect=sandbox):
            result = assets.refresh(self.config, "ITAM", "a" * 40, output,
                                    allow_project_code=True, codex="codex.exe")
        repo.assert_called_once_with(self.repo, "example/project", "a" * 40)
        self.assertEqual(result["status"], "refreshed")
        self.assertEqual((output / "frontend/node_modules/tool/index.js").read_text(), "module.exports=1")
        written = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(written["verification_environments"]["ITAM"]["frontend"]["snapshot"], str(output / "frontend"))
        self.assertEqual(written["token"], "DO-NOT-PRINT")

    def test_wrong_repository_is_rejected_before_project_execution_or_output_creation(self):
        assets.register(self.config, "ITAM", self.profile)
        def git(root, *args):
            return str(self.repo) if args[0] == "rev-parse" else "https://github.com/other/repo.git"
        with patch.object(assets, "_git", side_effect=git), patch.object(assets, "_sandbox") as sandbox:
            with self.assertRaisesRegex(assets.AssetError, "ORIGIN_MISMATCH"):
                assets.refresh(self.config, "ITAM", "a" * 40, self.base / "new",
                               allow_project_code=True, codex="codex.exe")
        sandbox.assert_not_called()
        self.assertFalse((self.base / "new").exists())

    def test_failure_before_export_preserves_old_config_and_snapshot(self):
        self._installed_node()
        old = Path(self.profile["frontend"]["snapshot"])
        old.mkdir()
        (old / "keep").write_text("previous valid assets")
        before = self.config.read_bytes()
        def git(root, *args):
            if args[:2] == ("worktree", "add"):
                frontend = Path(args[-2]) / "frontend"
                frontend.mkdir(parents=True)
                for name in ("package.json", "package-lock.json"):
                    (frontend / name).write_text("{}")
            return ""
        with patch.object(assets, "_repository"), patch.object(assets, "_git", side_effect=git), \
                patch.object(assets, "_sandbox", side_effect=assets.AssetError("ASSETS_SANDBOX_REFRESH_BLOCKED_OR_FAILED")):
            with self.assertRaises(assets.AssetError):
                assets.refresh(self.config, "ITAM", "a" * 40, self.base / "new",
                               allow_project_code=True, codex="codex.exe")
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual((old / "keep").read_text(), "previous valid assets")

    def test_gradle_refresh_bootstraps_missing_cache_and_resolves_runtime_dependencies(self):
        distribution = self.base / "gradle-9.5.1"
        (distribution / "lib/agents").mkdir(parents=True)
        for name in ("lib/gradle-gradle-cli-main-9.5.1.jar", "lib/agents/gradle-instrumentation-agent-9.5.1.jar"):
            (distribution / name).write_bytes(b"fixture")
        java = self.base / "jdk/bin/java.exe"
        java.parent.mkdir(parents=True)
        java.write_bytes(b"fixture")
        self.profile.pop("frontend")
        self.profile["gradle"] = {"project_dir": "backend", "distribution": str(distribution),
                                  "java_executable": str(java), "dependency_cache": str(self.base / "missing/modules-2")}
        assets.register(self.config, "ITAM", self.profile)
        output = self.base / "new"
        def git(root, *args):
            if args[:2] == ("worktree", "add"):
                wrapper = Path(args[-2]) / "backend/gradle/wrapper"
                wrapper.mkdir(parents=True)
                (wrapper / "gradle-wrapper.properties").write_text(
                    "distributionUrl=https\\://services.gradle.org/distributions/gradle-9.5.1-bin.zip\n")
            return "a" * 40 if args[:2] == ("rev-parse", "HEAD") else ""
        def sandbox(command, root, env, codex):
            self.assertEqual(command[-2:], ["lkhVerificationDependencies", "testClasses"])
            self.assertIn("--init-script", command)
            self.assertIn("--no-configuration-cache", command)
            self.assertNotIn("--offline", command)
            script = Path(command[command.index("--init-script") + 1]).read_text(encoding="utf-8")
            self.assertIn("testRuntimeClasspath", script)
            self.assertIn("runtimeClasspath", script)
            home = Path(env["GRADLE_USER_HOME"])
            self.assertIn("auto-download=false", (home / "gradle.properties").read_text())
            cache = home / "caches/modules-2"
            (cache / "files-2.1").mkdir(parents=True)
            (cache / "files-2.1/runtime-only.jar").write_bytes(b"resolved runtime dependency")
            (cache / "modules-2.lock").write_text("do not export")
        with patch.object(assets, "_repository"), patch.object(assets, "_git", side_effect=git), \
                patch.object(assets, "_sandbox", side_effect=sandbox):
            result = assets.refresh(self.config, "ITAM", "a" * 40, output,
                                    allow_project_code=True, codex="codex.exe")
        self.assertEqual(result["status"], "refreshed")
        self.assertEqual((output / "modules-2/files-2.1/runtime-only.jar").read_bytes(), b"resolved runtime dependency")
        self.assertFalse((output / "modules-2/modules-2.lock").exists())
        written = json.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(written["verification_environments"]["ITAM"]["gradle"]["dependency_cache"], str(output / "modules-2"))


if __name__ == "__main__":
    unittest.main()
