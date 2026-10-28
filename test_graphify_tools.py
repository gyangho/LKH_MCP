"""Unit tests for allowlisted Graphify MCP wrapper; no real code graph required."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import graphify_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class TestGraphifyTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        (self.root / "graphify-out").mkdir(parents=True)
        (self.root / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
        self.env = patch.dict(os.environ, {
            "GRAPHIFY_PROJECTS": f"ITAM={self.root}",
            "GRAPHIFY_ALLOW_UPDATE": "false",
            "GRAPHIFY_EXECUTABLE": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        mcp = FakeMCP()
        graphify_tools.register_graphify_tools(mcp)
        self.tools = mcp.tools

    def test_register_tools_and_list(self):
        self.assertEqual(set(self.tools), {
            "graphify_list_projects", "graphify_query", "graphify_explain", "graphify_path", "graphify_update"
        })
        out = self.tools["graphify_list_projects"]()
        self.assertTrue(out["projects"][0]["graph_exists"])
        self.assertFalse(out["update_enabled"])
        self.assertNotIn(str(self.root), str(out))

    def test_unauthorized_project_refused(self):
        with self.assertRaises(ValueError):
            self.tools["graphify_query"]("SECRET", "authentication")

    def test_query_and_path_arguments_are_fixed(self):
        with patch.object(graphify_tools, "_graphify_binary", return_value="graphify"):
            with patch.object(graphify_tools.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "node ok"
                run.return_value.stderr = ""
                response = self.tools["graphify_query"]("ITAM", "collector login", 500, True)
                self.assertTrue(response["success"])
                args = run.call_args.args[0]
                self.assertEqual(args, ["graphify", "query", "collector login", "--budget", "500", "--dfs"])
                self.assertFalse(run.call_args.kwargs["shell"])
                self.assertEqual(run.call_args.kwargs["env"]["GRAPHIFY_BACKEND"], "none")
                self.tools["graphify_path"]("ITAM", "Login", "Collector")
                self.assertEqual(run.call_args.args[0][1:], ["path", "Login", "Collector"])

    def test_update_refused_by_default(self):
        with self.assertRaises(PermissionError):
            self.tools["graphify_update"]("ITAM")

    def test_update_calls_only_fixed_command(self):
        with patch.dict(os.environ, {"GRAPHIFY_ALLOW_UPDATE": "true"}):
            with patch.object(graphify_tools, "_graphify_binary", return_value="graphify"):
                with patch.object(graphify_tools.subprocess, "run") as run:
                    run.return_value.returncode = 0
                    run.return_value.stdout = "updated"
                    run.return_value.stderr = ""
                    self.assertTrue(self.tools["graphify_update"]("ITAM")["success"])
                    self.assertEqual(run.call_args.args[0][1:], ["update", "."])

    def test_missing_graph_rejected(self):
        (self.root / "graphify-out" / "graph.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.tools["graphify_explain"]("ITAM", "Collector")

    def test_bad_input_rejected(self):
        with self.assertRaises(ValueError):
            self.tools["graphify_query"]("ITAM", "--help")
        with self.assertRaises(ValueError):
            self.tools["graphify_query"]("ITAM", "hello\nworld")
        with self.assertRaises(ValueError):
            self.tools["graphify_explain"]("ITAM", "-bad")
        with self.assertRaises(ValueError):
            self.tools["graphify_query"]("ITAM", "hello", 5000)

    def test_rejects_relative_paths(self):
        with patch.dict(os.environ, {"GRAPHIFY_PROJECTS": "ITAM=relative/repo"}):
            with self.assertRaises(ValueError):
                self.tools["graphify_list_projects"]()


if __name__ == "__main__":
    unittest.main()
