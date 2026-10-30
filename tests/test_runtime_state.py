"""Runtime telemetry and current SQLite-backed toggle regression tests."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import runtime_state as state
import settings_store

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
        folder = Path(temp.name)
        env = patch.dict(os.environ, {
            "MCP_DB_PATH": str(folder / "config.sqlite3"),
            "MCP_BOOTSTRAP_FILE": str(folder / "none.json"),
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        dotenv_mock = patch("dotenv.load_dotenv", return_value=False)
        dotenv_mock.start()
        self.addCleanup(dotenv_mock.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))

    def test_flags_persist_and_reload(self):
        result = state.change_flag("CODEX_AGENT_ENABLED", True, "admin@example.test")
        self.assertTrue(result["saved"])
        self.assertEqual(os.environ["CODEX_AGENT_ENABLED"], "true")
        settings_store._READY = False
        state.initialize_state()
        self.assertTrue(settings_store.get("CODEX_AGENT_ENABLED"))

    def test_only_known_boolean_flags(self):
        for key, val in (("ORACLE_PASSWORD", True), ("CODEX_AGENT_ENABLED", "true"),
                         ("GIT_ALLOW_PUSH", True), ("CODEX_AGENT_ENABLED", 1)):
            with self.subTest(key=key, value=val), self.assertRaises(ValueError):
                state.change_flag(key, val, "admin@example.test")

    def test_flags_exclude_old_permissions_and_secrets(self):
        keys = {x["key"] for x in state.flags_snapshot()}
        self.assertIn("CODEX_AGENT_ENABLED", keys)
        for hidden in ("ORACLE_PASSWORD", "CODEX_DELEGATION_ENABLED", "GIT_ALLOW_PUSH",
                       "GRAPHIFY_ALLOW_UPDATE"):
            self.assertNotIn(hidden, keys)

    def test_telemetry_never_logs_args(self):
        mcp = DummyMCP()
        state.instrument_tools(mcp)
        @mcp.tool()
        def example(secret: str):
            return {"success": True}
        example("DO_NOT_LOG_SECRET_123")
        info = state.telemetry()
        self.assertGreaterEqual(info["requests"]["total"], 1)
        self.assertNotIn("DO_NOT_LOG_SECRET_123", str(info))
        self.assertTrue(any(i["tool"] == "example" for i in info["recent"]))
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
