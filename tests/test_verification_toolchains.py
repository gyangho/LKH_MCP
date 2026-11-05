"""Toolchain registration and staged build-tool checks through preparation interface."""
import subprocess
import json
import shutil
import unittest
from pathlib import Path

from tests import test_verification_environment as fixtures
import verification_environment as verification


class ToolchainPreparationTests(unittest.TestCase):
    prepare = fixtures.PreparationTests.prepare

    def setUp(self):
        fixtures.PreparationTests.setUp(self)
        self.run.return_value = subprocess.CompletedProcess([], 0, "LKH_DEPENDENCY_CONFIGURATIONS=4\n")

    def add_jdk(self, version="17.0.12"):
        home = self.base / "approved" / "jdk-compile"
        (home / "bin").mkdir(parents=True)
        (home / "bin/java.exe").write_bytes(b"fixture")
        (home / "bin/javac.exe").write_bytes(b"fixture")
        (home / "release").write_text('JAVA_VERSION="' + version + '"\n')
        self.profile["gradle"]["java_toolchain_homes"] = [str(home)]
        self.run.return_value = subprocess.CompletedProcess([], 0,
            f" + Test JDK\n | Location: {home}\n | Language Version: 17\n | Is JDK: true\n"
            "LKH_DEPENDENCY_CONFIGURATIONS=4\n")
        return home

    def test_explicit_compiler_is_distinct_from_runtime_and_registered_offline(self):
        home = self.add_jdk()
        verification.validate_profiles({"project": self.profile})
        manifest, env = self.prepare()
        self.assertEqual(env["JAVA_HOME"], str(self.java.parent.parent))
        self.assertEqual(manifest["gradle"]["java_toolchains"],
                         [{"home": str(home), "version": "17.0.12"}])
        settings = (Path(env["GRADLE_USER_HOME"]) / "gradle.properties").read_text(encoding="utf-8")
        self.assertIn("org.gradle.java.installations.auto-detect=false", settings)
        self.assertIn("org.gradle.java.installations.auto-download=false", settings)
        self.assertIn("org.gradle.java.installations.paths=" +
                      json.dumps(home.as_posix(), ensure_ascii=True)[1:-1], settings)
        commands = [call.args[0] for call in self.run.call_args_list]
        self.assertEqual([command[-1] for command in commands[:3]],
                         ["--version", "help", "javaToolchains"])
        self.assertEqual(manifest["tests_executed"], 0)
        self.assertEqual(manifest["gradle"]["dependency_configurations"], 4)
        self.assertEqual(manifest["gradle"]["dependency_preflight"], "passed")
        self.assertEqual(commands[3][-1], "lkhVerificationDependencies")

    def test_project_without_java_configurations_does_not_claim_dependencies_verified(self):
        self.run.return_value = subprocess.CompletedProcess([], 0, "LKH_DEPENDENCY_CONFIGURATIONS=0\n")
        manifest, _ = self.prepare()
        self.assertEqual(manifest["gradle"]["dependency_preflight"], "not_applicable")
        self.assertEqual(manifest["gradle"]["dependency_configurations"], 0)

    def test_missing_dependency_readiness_report_blocks_model_execution(self):
        self.run.return_value = subprocess.CompletedProcess([], 0, "Other task output")
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_DEPENDENCY_REPORT_UNAVAILABLE"):
            self.prepare()

    def test_jre_without_compiler_blocks_before_any_project_execution(self):
        home = self.add_jdk()
        (home / "bin/javac.exe").unlink()
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_JAVA_TOOLCHAIN_UNAVAILABLE"):
            self.prepare()
        self.run.assert_not_called()

    def test_unparseable_toolchain_version_blocks_before_project_execution(self):
        self.add_jdk("<private>")
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_JAVA_TOOLCHAIN_VERSION_INVALID"):
            self.prepare()
        self.run.assert_not_called()

    def test_paths_cannot_inject_gradle_properties(self):
        self.profile["gradle"]["java_toolchain_homes"] = [str(self.base / "jdk\nproperty=true")]
        with self.assertRaises(verification.PreparationError):
            verification.validate_profiles({"project": self.profile})

    def test_missing_project_toolchain_is_classified_without_raw_error(self):
        self.add_jdk()
        self.run.return_value = subprocess.CompletedProcess([], 1,
            "private-token=SECRET Cannot find a Java installation on your machine matching this tasks requirements")
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_JAVA_TOOLCHAIN_MISSING") as caught:
            self.prepare()
        self.assertNotIn("SECRET", str(caught.exception))

    def test_unsupported_runtime_is_classified(self):
        self.run.return_value = subprocess.CompletedProcess([], 1,
            "SECRET UnsupportedClassVersionError runtime")
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_JAVA_RUNTIME_UNSUPPORTED") as caught:
            self.prepare()
        self.assertNotIn("SECRET", str(caught.exception))

    def test_gradle_ignoring_registered_compiler_is_not_a_success(self):
        self.add_jdk()
        self.run.return_value = subprocess.CompletedProcess([], 0,
            "Invalid Java installation ignored; SECRET")
        with self.assertRaisesRegex(verification.PreparationError, "VERIFICATION_JAVA_TOOLCHAIN_NOT_DETECTED") as caught:
            self.prepare()
        self.assertNotIn("SECRET", str(caught.exception))

    def test_frontend_smoke_uses_staged_project_dependencies(self):
        manifest, _ = self.prepare()
        self.assertEqual(manifest["frontend"]["dependency_preflight"], "passed")
        command = self.run.call_args_list[-1].args[0]
        self.assertEqual(command[-1], str(self.project))
        self.assertEqual(Path(command[-2]).name, "frontend-preflight.cjs")
        self.assertTrue(Path(command[-2]).is_relative_to(self.root))

    def test_frontend_smoke_detects_incomplete_package_with_real_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node executable unavailable on test host")
        self.prepare()
        script = self.root / ".lkh-verification/frontend-preflight.cjs"
        # Only this trusted staged smoke script runs; no project build/install is invoked.
        self.runner.stop()
        result = subprocess.run([node, str(script), str(self.project)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "Frontend dependency preflight failed")
        (self.project / "node_modules/tool/package.json").write_text('{"name":"tool"}')
        result = subprocess.run([node, str(script), str(self.project)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
