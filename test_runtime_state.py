"""Tests for persistence, read-only telemetry and MCP tool tracking."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_state as state


class DummyMCP:
    def __init__(self):
        self.handlers = {}
    def tool(self):
        def decorator(fn):
            self.handlers[fn.__name__] = fn
            return fn
        return decorator


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        env = patch.dict(os.environ, {
            "MCP_STATE_DIR": str(self.folder),
            "GIT_ALLOW_COMMIT": "false",
            "GIT_ALLOW_PUSH": "false",
            "GRAPHIFY_ALLOW_UPDATE": "false",
        })
        env.start()
        self.addCleanup(env.stop)

    def test_flags_persist_and_reload(self):
        result = state.change_flag("GIT_ALLOW_COMMIT", True, "admin@example.test")
        self.assertTrue(result["saved"])
        self.assertEqual(os.environ["GIT_ALLOW_COMMIT"], "true")
        stored = json.loads((self.folder / "runtime-settings.json").read_text())
        self.assertTrue(stored["GIT_ALLOW_COMMIT"])
        os.environ["GIT_ALLOW_COMMIT"] = "false"
        state.initialize_state()
        self.assertEqual(os.environ["GIT_ALLOW_COMMIT"], "true")

    def test_only_known_boolean_flags(self):
        for key, val in (("ORACLE_PASSWORD", True), ("GIT_ALLOW_PUSH", "true"),
                         ("GIT_ALLOW_COMMIT", 1)):
            with self.subTest(key=key, val=val):
                with self.assertRaises(ValueError):
                    state.change_flag(key, val, "admin@example.test")

    def test_invalid_config_is_rejected(self):
        path = self.folder / "runtime-settings.json"
        path.write_text('{"ORACLE_PASSWORD":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            state.initialize_state()

    def test_telemetry_has_no_credentials_or_tool_args(self):
        mcp = DummyMCP()
        state.instrument_tools(mcp)
        @mcp.tool()
        def example(secret: str):
            return {"success": True}
        example("DO_NOT_LOG_SECRET_123")
        info = state.telemetry()
        self.assertGreaterEqual(info["requests"]["total"], 1)
        self.assertNotIn("DO_NOT_LOG_SECRET_123", str(info))
        self.assertTrue(any(item["tool"] == "example" for item in info["recent"]))
        self.assertIn("version", info)

    def test_tool_failure_recording(self):
        mcp = DummyMCP()
        state.instrument_tools(mcp)
        @mcp.tool()
        def fail():
            raise RuntimeError("test")
        before = state.telemetry()["requests"]["failed"]
        with self.assertRaises(RuntimeError):
            fail()
        self.assertEqual(state.telemetry()["requests"]["failed"], before + 1)


if __name__ == "__main__":
    unittest.main()
