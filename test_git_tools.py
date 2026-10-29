"""Local Git MCP security tests. Network push is always mocked."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import git_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}
    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


class TestGitTools(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "ITAM"
        (self.root / ".git").mkdir(parents=True)
        env = patch.dict(os.environ, {
            "GRAPHIFY_PROJECTS": f"ITAM={self.root}",
            "GIT_ALLOWED_REPOS": "ITAM=gyangho/ITAM",
            "GIT_ALLOW_PUSH": "false",
            "ORACLE_PASSWORD": "secret",
        })
        env.start()
        self.addCleanup(env.stop)
        mcp = FakeMCP()
        git_tools.register_git_tools(mcp)
        self.tools = mcp.tools
        self.sha = "a" * 40

    def test_tools_registered_and_disabled(self):
        self.assertEqual(set(self.tools), {"git_list_projects", "git_status", "git_diff", "git_push"})
        data = self.tools["git_list_projects"]()
        self.assertFalse(data["push_enabled"])
        self.assertNotIn(str(self.root), str(data))

    def test_unknown_project(self):
        with self.assertRaises(ValueError):
            self.tools["git_status"]("unknown")

    def test_bad_remote(self):
        with patch.object(git_tools, "_git", side_effect=[str(self.root), "https://evil.example/gyangho/ITAM"]):
            with self.assertRaises(ValueError):
                self.tools["git_status"]("ITAM")

    def test_status_and_diff(self):
        with patch.object(git_tools, "_git", side_effect=[
            str(self.root), "https://github.com/gyangho/ITAM.git",
            "main", self.sha, " M src/App.tsx\n"
        ]):
            self.assertFalse(self.tools["git_status"]("ITAM")["clean"])
        with patch.object(git_tools, "_git", side_effect=[
            str(self.root), "git@github.com:gyangho/ITAM.git", "diff --git a/x b/x"
        ]) as run:
            self.assertIn("diff --git", self.tools["git_diff"]("ITAM", True)["diff"])
            self.assertIn("--cached", run.call_args.args)

    def test_push_requires_opt_in(self):
        with self.assertRaises(PermissionError):
            self.tools["git_push"]("ITAM", self.sha)

    def test_push_expected_sha_and_clean(self):
        with patch.dict(os.environ, {"GIT_ALLOW_PUSH": "true"}):
            with patch.object(git_tools, "_git", side_effect=[
                str(self.root), "https://github.com/gyangho/ITAM",
                "main", self.sha, "", "done"
            ]) as run:
                self.assertTrue(self.tools["git_push"]("ITAM", self.sha)["success"])
                self.assertEqual(run.call_args.args[1:],
                                 ("push", "--porcelain", "origin", "HEAD:refs/heads/main"))
            with patch.object(git_tools, "_git", side_effect=[
                str(self.root), "https://github.com/gyangho/ITAM",
                "main", self.sha, " M x"
            ]):
                with self.assertRaises(RuntimeError):
                    self.tools["git_push"]("ITAM", self.sha)

    def test_secret_environment_not_inherited(self):
        self.assertNotIn("ORACLE_PASSWORD", git_tools._env())
        self.assertEqual(git_tools._env()["GIT_TERMINAL_PROMPT"], "0")

    def test_allowlist_invalid(self):
        with patch.dict(os.environ, {"GIT_ALLOWED_REPOS": "ITAM=bad/repo/extra"}):
            with self.assertRaises(ValueError):
                self.tools["git_list_projects"]()


if __name__ == "__main__":
    unittest.main()
