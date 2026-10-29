"""Integration tests of AI-reviewed Git commits against a disposable local repository.

No network access, GitHub authentication or push is used. Requires local git.exe.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import git_commit_tools as gc


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


@unittest.skipUnless(shutil.which("git"), "Git executable is not installed")
class TestCommitTools(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "ITAM"
        self.root.mkdir()
        self._run("init", "-b", "main")
        self._run("config", "user.name", "MCP Test")
        self._run("config", "user.email", "mcp-test@example.invalid")
        self._run("remote", "add", "origin", "https://github.com/gyangho/ITAM.git")
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('before')\n", encoding="utf-8")
        self._run("add", "src/main.py")
        self._run("commit", "-m", "Initial test commit")
        self.old_head = self._run("rev-parse", "HEAD").strip()

        env = patch.dict(os.environ, {
            "GRAPHIFY_PROJECTS": f"ITAM={self.root}",
            "GIT_ALLOWED_REPOS": "ITAM=gyangho/ITAM",
            "GIT_ALLOW_COMMIT": "true",
            "GIT_EXECUTABLE": "",
        })
        env.start()
        self.addCleanup(env.stop)
        mcp = FakeMCP()
        gc.register_git_commit_tools(mcp)
        self.tools = mcp.tools

    def _run(self, *args):
        result = subprocess.run(
            ["git", *args], cwd=self.root, check=True,
            text=True, capture_output=True, encoding="utf-8",
        )
        return result.stdout

    def _modify(self):
        (self.root / "src" / "main.py").write_text("print('after')\n", encoding="utf-8")

    def test_registration_and_disabled_by_default(self):
        self.assertEqual(set(self.tools),
                         {"git_stage_paths", "git_preview_commit", "git_commit"})
        self._modify()
        with patch.dict(os.environ, {"GIT_ALLOW_COMMIT": "false"}):
            with self.assertRaises(PermissionError):
                self.tools["git_stage_paths"]("ITAM", ["src/main.py"], self.old_head)

    def test_rejects_secret_paths_and_directories(self):
        for value in (".env", ".env.production", "../escape", "/etc/passwd",
                      "src/", "src/../escape", "a\\b", ".git/config",
                      "id_ed25519", "config.pem", "secret_key.txt"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gc._safe_path(self.root, value)

    def test_end_to_end_stage_preview_commit(self):
        self._modify()
        staged = self.tools["git_stage_paths"](
            "ITAM", ["src/main.py"], self.old_head
        )
        self.assertEqual(staged["staged_files"], ["src/main.py"])
        preview = self.tools["git_preview_commit"]("ITAM")
        self.assertEqual(preview["head"], self.old_head)
        self.assertEqual(preview["diff_sha256"], hashlib.sha256(
            preview["patch"].encode("utf-8")
        ).hexdigest())
        self.assertIn("print('after')", preview["patch"])
        committed = self.tools["git_commit"](
            "ITAM", preview["head"], preview["diff_sha256"],
            "fix: update local example", "Review exact staged source change"
        )
        self.assertTrue(committed["success"])
        self.assertFalse(committed["pushed"])
        self.assertEqual(committed["commit"], self._run("rev-parse", "HEAD").strip())
        self.assertEqual(self._run("status", "--porcelain"), "")
        self.assertIn("fix: update local example", self._run("log", "-1", "--format=%s"))

    def test_wrong_digest_refuses_commit(self):
        self._modify()
        self.tools["git_stage_paths"]("ITAM", ["src/main.py"], self.old_head)
        with self.assertRaises(RuntimeError):
            self.tools["git_commit"](
                "ITAM", self.old_head, "0" * 64, "fix: should not commit"
            )
        self.assertEqual(self.old_head, self._run("rev-parse", "HEAD").strip())

    def test_preexisting_staged_change_refused(self):
        self._modify()
        self._run("add", "src/main.py")
        with self.assertRaises(RuntimeError):
            self.tools["git_stage_paths"]("ITAM", ["src/main.py"], self.old_head)

    def test_unstaged_change_cannot_sneak_into_commit(self):
        self._modify()
        self.tools["git_stage_paths"]("ITAM", ["src/main.py"], self.old_head)
        preview = self.tools["git_preview_commit"]("ITAM")
        # An unrelated file staged after preview invalidates the digest.
        (self.root / "src" / "other.py").write_text("print('unreviewed')\n", encoding="utf-8")
        self._run("add", "src/other.py")
        with self.assertRaises(RuntimeError):
            self.tools["git_commit"](
                "ITAM", preview["head"], preview["diff_sha256"],
                "feat: should not commit another file"
            )
        self.assertEqual(self.old_head, self._run("rev-parse", "HEAD").strip())

    def test_refuse_unreviewable_large_diff(self):
        (self.root / "src" / "big.py").write_text("x" * 49000, encoding="utf-8")
        with self.assertRaises(ValueError):
            self.tools["git_stage_paths"]("ITAM", ["src/big.py"], self.old_head)
        self.assertEqual(self.old_head, self._run("rev-parse", "HEAD").strip())

    def test_message_validation(self):
        for subject in ("", "bad\nmessage", "bad\x00message", "x" * 101):
            with self.subTest(subject=subject):
                with self.assertRaises(ValueError):
                    self.tools["git_commit"](
                        "ITAM", self.old_head, "0" * 64, subject
                    )


if __name__ == "__main__":
    unittest.main()
