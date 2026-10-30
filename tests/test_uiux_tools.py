"""Self-contained smoke tests for the adapter, without Oracle or GitHub access."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import uiux_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn
        return deco


class TestUiuxTools(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        script = Path(self.tempdir.name) / "search.py"
        script.write_text(
            'import sys, json\n'
            'print(json.dumps({"args": sys.argv[1:], "count": 2, "results": [{"x": "ok"}]}))\n',
            encoding="utf-8",
        )
        self.mock_script = patch.object(uiux_tools, "SCRIPT", script)
        self.mock_script.start()
        self.addCleanup(self.mock_script.stop)
        # Adapter unit tests must never spawn the host's real Python executable.
        def fake_run(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 0,
                stdout=json.dumps({"args": command[2:], "count": 2, "results": [{"x": "ok"}]}),
                stderr="",
            )
        runner = patch.object(uiux_tools.subprocess, "run", side_effect=fake_run)
        runner.start()
        self.addCleanup(runner.stop)
        mcp = FakeMCP()
        uiux_tools.register_uiux_tools(mcp)
        self.tools = mcp.tools

    def test_registers_three_tools(self):
        self.assertEqual(set(self.tools), {"uiux_search", "uiux_stack_guidelines", "uiux_generate_design_system", "uiux_diagnostics"})

    def test_search_uses_json_and_domain(self):
        result = self.tools["uiux_search"]("accessible navigation", "ux", 2)
        self.assertEqual(result["count"], 2)
        self.assertIn("--json", result["args"])
        self.assertIn("ux", result["args"])

    def test_stack_search(self):
        result = self.tools["uiux_stack_guidelines"]("form validation", "react")
        self.assertIn("--stack", result["args"])
        self.assertIn("react", result["args"])

    def test_unsupported_stack_returns_actionable_error(self):
        result = self.tools["uiux_stack_guidelines"]("admin", "html")
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_STACK")
        self.assertEqual(result["error"]["suggested_tool"], "uiux_search")
        self.assertIn("react", result["error"]["supported_stacks"])

    def test_design_system_is_read_only(self):
        result = self.tools["uiux_generate_design_system"]("SaaS dashboard", "ITAM")
        self.assertIn("--design-system", result["args"])
        self.assertNotIn("--persist", result["args"])

    def test_missing_python_executable_has_actionable_error(self):
        with patch.object(uiux_tools.subprocess, "run", side_effect=FileNotFoundError("missing")):
            with self.assertRaisesRegex(RuntimeError, "UIUX_PYTHON_EXECUTABLE"):
                self.tools["uiux_search"]("navigation")

    def test_blocks_bad_inputs(self):
        with self.assertRaises(ValueError):
            self.tools["uiux_search"]("design", "nonsense")
        with self.assertRaises(ValueError):
            self.tools["uiux_search"]("design", "ux", 100)
        with self.assertRaises(ValueError):
            self.tools["uiux_search"]("--persist", "ux")


if __name__ == "__main__":
    unittest.main()
