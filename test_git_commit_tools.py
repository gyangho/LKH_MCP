"""Unit tests: safe AI-generated Git commit workflow; all Git commands are mocked."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import git_commit_tools as gc


class FakeMCP:
    def __init__(self):
        self.tools = {}
    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


class TestCommitTools(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ITAM"
        (self.root / ".git").mkdir(parents=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
        env = patch.dict(os.environ, {
            "GRAPHIFY_PROJECTS": f"ITAM={self.root}",
            "GIT_ALLOWED_REPOS": "ITAM=gyangho/ITAM",
            "GIT_ALLOW_COMMIT": "true",
        })
        env.start()
        self.addCleanup(env.stop)
        mcp = FakeMCP()
        gc.register_git_commit_tools(mcp)
        self.t = mcp.tools
        self.head = "a" * 40
        self.patch_text = "diff --git a/src/main.py b/src/main.py\n+print('ok')\n"
        self.digest = hashlib.sha256(self.patch_text.encode()).hexdigest()

    def test_paths_block_secrets_and_escape(self):
        for path in (".env", ".env.production", "../outside", "/etc/passwd",
                     "a\\b", "src/", "src/../secrets.txt", ".git/config",
                     "secret_key.txt", "id_ed25519", "file.pem"):
            with self.assertRaises(ValueError, msg=path):
                gc._safe_path(self.root, path)

    def test_stage_is_opt_in_and_explicit(self):
        with patch.dict(os.environ, {"GIT_ALLOW_COMMIT": "false"}):
            with self.assertRaises(PermissionError):
                self.t["git_stage_paths"]("ITAM", ["src/main.py"], self.head)
        calls = [
            str(self.root), "https://github.com/gyangho/ITAM",
            "main", self.head, "", "", self.patch_text, "src/main.py\x00",
        ]
        with patch.object(gc, "_git", side_effect=calls) as run:
            output = self.t["git_stage_paths"]("ITAM", ["src/main.py"], self.head)
            self.assertEqual(output["staged_files"], ["src/main.py"])
            self.assertTrue(any(call.args[1:5] == ("add", "-A", "--", "src/main.py")
                                for call in run.call_args_list))

    def test_stage_refuses_preexisting_index(self):
        calls = [str(self.root), "https://github.com/gyangho/ITAM",
                 "main", self.head, "src/other.py\n"]
        with patch.object(gc, "_git", side_effect=calls):
            with self.assertRaises(RuntimeError):
                self.t["git_stage_paths"]("ITAM", ["src/main.py"], self.head)

    def test_preview_returns_full_patch_and_hash(self):
        calls = [str(self.root), "https://github.com/gyangho/ITAM",
                 "main", self.head, self.patch_text, "src/main.py\x00"]
        with patch.object(gc, "_git", side_effect=calls):
            preview = self.t["git_preview_commit"]("ITAM")
        self.assertEqual(preview["diff_sha256"], self.digest)
        self.assertEqual(preview["patch"], self.patch_text)

    def test_commit_requires_matching_hash(self):
        calls = [str(self.root), "https://github.com/gyangho/ITAM",
                 "main", self.head, self.patch_text, "src/main.py\x00"]
        with patch.object(gc, "_git", side_effect=calls):
            with self.assertRaises(RuntimeError):
                self.t["git_commit"]("ITAM", self.head, "0" * 64, "fix: test")

    def test_commit_calls_only_fixed_git_commit(self):
        calls = [str(self.root), "https://github.com/gyangho/ITAM",
                 "main", self.head, self.patch_text, "src/main.py\x00",
                 "committed", "main", "b" * 40]
        with patch.object(gc, "_git", side_effect=calls) as run:
            result = self.t["git_commit"]("ITAM", self.head, self.digest,
                                          "fix: correct tests", "Verify login flow")
        self.assertEqual(result["commit"], "b" * 40)
        self.assertFalse(result["pushed"])
        commit_call = run.call_args_list[6]
        self.assertEqual(commit_call.args[1], "-c")
        self.assertIn("commit", commit_call.args)
        self.assertIn("commit.gpgsign=false", commit_call.args)

    def test_message_input_validation(self):
        for message in ("", "hello\nworld", "\x00bad", "x" * 101):
            with self.assertRaises(ValueError):
                self.t["git_commit"]("ITAM", self.head, self.digest, message)

    def test_diff_max_limit_and_no_changes(self):
        with patch.object(gc, "_git", side_effect=["x" * 50000, "src/main.py\x00"]):
            with self.assertRaises(ValueError):
                gc._staged(self.root)
        with patch.object(gc, "_git", side_effect=["", ""]):
            with self.assertRaises(ValueError):
                gc._staged(self.root)


if __name__ == "__main__":
    unittest.main()
