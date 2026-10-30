"""Runtime telemetry and SQLite-backed toggle regression tests."""
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
            "GIT_ALLOW_COMMIT": "false",
            "GIT_ALLOW_PUSH": "false",
            "GRAPHIFY_ALLOW_UPDATE": "false",
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        dotenv_mock = patch("dotenv.load_dotenv", return_value=False)
        dotenv_mock.start()
        self.addCleanup(dotenv_mock.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))

    def test_flags_persist_and_reload(self):
        result = state.change_flag("GIT_ALLOW_COMMIT", True, "admin@example.test")
        self.assertTrue(result["saved"])
        self.assertEqual(os.environ["GIT_ALLOW_COMMIT"], "true")
        self.assertTrue(settings_store.get("GIT_ALLOW_COMMIT"))
        os.environ["GIT_ALLOW_COMMIT"] = "false"
        settings_store._READY = False
        state.initialize_state()
        self.assertEqual(os.environ["GIT_ALLOW_COMMIT"], "true")

    def test_only_known_boolean_flags(self):
        for key, val in (("ORACLE_PASSWORD", True), ("GIT_ALLOW_PUSH", "true"),
                         ("GIT_ALLOW_COMMIT", 1)):
            with self.subTest(key=key, val=val):
                with self.assertRaises(ValueError):
                    state.change_flag(key, val, "admin@example.test")

    def test_flags_never_expose_database_password(self):
        keys = {x["key"] for x in state.flags_snapshot()}
        self.assertNotIn("ORACLE_PASSWORD", keys)
        self.assertIn("CODEX_DELEGATION_ENABLED", keys)

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
