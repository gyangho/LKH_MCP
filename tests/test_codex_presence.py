"""Phase 0: Agent presence, trust boundaries, and Windows diagnostic probes."""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import codex_bridge as bridge
import codex_presence as presence
import codex_agent_routes
import codex_admin


CAPS = {"git_installed": True, "codex_installed": True,
        "codex_authenticated": True, "graphify_installed": False}


class PresenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "presence.sqlite3"
        self.clock = [1_000_000]
        self.settings = {"CODEX_AGENT_ENABLED": True,
                         "GIT_ALLOWED_REPOS": "LKH_MCP=gyangho/LKH_MCP",
                         "CODEX_MAX_RUNS_PER_DAY": 30}
        for patcher in [
            patch.object(bridge.settings_store, "get", side_effect=lambda k: self.settings[k]),
            patch.object(bridge.settings_store, "_connect",
                         side_effect=lambda: sqlite3.connect(self.db)),
            patch.object(bridge, "_now", side_effect=lambda: self.clock[0]),
            patch.dict(os.environ, {"CODEX_AGENT_TOKEN": "X" * 48}),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def send(self, **kwargs):
        payload = {"agent_id": "win-01", "projects": ["LKH_MCP"],
                   "capabilities": CAPS.copy()}
        payload.update(kwargs)
        return presence.heartbeat(**payload)

    def test_connected_then_offline_and_secret_not_exposed(self):
        self.assertTrue(self.send()["ok"])
        snap = presence.agents_snapshot()
        self.assertTrue(snap["agents"][0]["online"])
        self.assertEqual(snap["agents"][0]["agent_id"], "win-01")
        self.assertTrue(snap["agents"][0]["capabilities"]["codex_authenticated"])
        self.assertNotIn("X" * 48, str(snap))
        self.clock[0] += 46
        self.assertFalse(presence.agents_snapshot()["agents"][0]["online"])
        self.send()
        self.assertTrue(presence.agents_snapshot()["agents"][0]["online"])

    def test_disabled_fails_closed(self):
        self.settings["CODEX_AGENT_ENABLED"] = False
        with self.assertRaises(PermissionError):
            self.send()
        self.assertFalse(presence.agents_snapshot()["enabled"])

    def test_invalid_identity_projects_capabilities_rejected(self):
        bad_values = [
            {"agent_id": "../escape"},
            {"agent_id": ""},
            {"projects": ["OTHER"]},
            {"projects": ["LKH_MCP", "LKH_MCP"]},
            {"projects": []},
            {"capabilities": {**CAPS, "hostname": True}},
            {"capabilities": {**CAPS, "codex_installed": "true"}},
            {"capabilities": {"git_installed": True}},
        ]
        for values in bad_values:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.send(**values)
        self.assertEqual(presence.agents_snapshot()["agents"], [])

    def test_busy_is_based_on_server_claim_not_agent_input(self):
        self.send()
        job = bridge.enqueue("LKH_MCP", "main", "a" * 40, instructions="verify tests")
        self.assertIsNotNone(bridge.claim("win-01", ["LKH_MCP"])["job"])
        agent = presence.agents_snapshot()["agents"][0]
        self.assertTrue(agent["busy"])
        self.assertEqual(agent["current_task"]["id"], job["id"])

    def test_token_missing_does_not_report_online(self):
        self.send()
        with patch.dict(os.environ, {"CODEX_AGENT_TOKEN": ""}):
            snap = presence.agents_snapshot()
            self.assertFalse(snap["token_configured"])
            self.assertFalse(snap["agents"][0]["online"])


class RoutesTests(unittest.IsolatedAsyncioTestCase):
    class FakeMCP:
        def __init__(self):
            self.routes = {}

        def custom_route(self, path, methods):
            def wrapper(fn):
                self.routes[path] = fn
                return fn
            return wrapper

    @staticmethod
    def request(path, body=b"{}", token="Bearer " + "X" * 48,
                content_type="application/json"):
        from starlette.requests import Request
        headers = [(b"content-type", content_type.encode()),
                   (b"authorization", token.encode())]
        scope = {"type": "http", "http_version": "1.1", "method": "POST",
                 "scheme": "http", "path": path, "root_path": "",
                 "query_string": b"", "headers": headers}
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        return Request(scope, receive)

    async def test_heartbeat_route_rejects_bad_auth_and_payload(self):
        app = self.FakeMCP()
        codex_agent_routes.register_agent_routes(app)
        route = app.routes["/admin/agent/heartbeat"]
        with patch.object(codex_agent_routes, "check_agent_token",
                          side_effect=lambda t: t == "Bearer valid"):
            self.assertEqual((await route(self.request("/admin/agent/heartbeat"))).status_code, 401)
            bad = self.request("/admin/agent/heartbeat", token="Bearer valid",
                               body=b'{"unexpected":true}')
            self.assertEqual((await route(bad)).status_code, 400)
            with patch.object(codex_agent_routes, "heartbeat", side_effect=PermissionError):
                valid = json.dumps({"agent_id": "win-01", "projects": ["LKH_MCP"],
                                    "capabilities": CAPS}).encode()
                self.assertEqual((await route(self.request("/admin/agent/heartbeat",
                                                           valid, "Bearer valid"))).status_code, 403)
            with patch.object(codex_agent_routes, "heartbeat", return_value={"ok": True}) as hb:
                result = await route(self.request("/admin/agent/heartbeat",
                                                  valid, "Bearer valid"))
                self.assertEqual(result.status_code, 200)
                self.assertEqual(json.loads(result.body), {"ok": True})
                hb.assert_called_once()

    async def test_admin_endpoint_requires_session(self):
        app = self.FakeMCP()
        codex_admin.register_codex_admin_routes(app)
        endpoint = app.routes["/admin/api/codex/agents"]
        request = self.request("/admin/api/codex/agents")
        with patch.object(codex_admin, "_verify_access", side_effect=codex_admin.AdminUnauthorized):
            with patch.object(codex_admin, "_auth_response",
                              return_value=__import__("starlette.responses",
                                                      fromlist=["JSONResponse"]).JSONResponse(
                                                          {"error": "no"}, status_code=401)):
                self.assertEqual((await endpoint(request)).status_code, 401)
        with patch.object(codex_admin, "_verify_access", return_value="admin"):
            with patch.object(codex_admin, "agents_snapshot", return_value={"agents": []}):
                result = await endpoint(request)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(json.loads(result.body), {"agents": []})


class WindowsDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from windows_agent import agent
        self.agent = agent

    def test_capability_probe_never_exposes_login_output(self):
        from subprocess import CompletedProcess
        with patch.object(self.agent.shutil, "which",
                          side_effect=lambda name: {
                              "git": "git.exe", "codex": "codex.cmd"
                          }.get(name)):
            with patch.object(self.agent.subprocess, "run",
                              return_value=CompletedProcess([], 0, "private", "secret")):
                self.assertEqual(self.agent.probe_capabilities(), CAPS)

    def test_probe_handles_missing_or_unauthed_codex(self):
        with patch.object(self.agent.shutil, "which", return_value=None):
            self.assertFalse(self.agent.probe_capabilities()["codex_authenticated"])
        with patch.object(self.agent.shutil, "which", return_value="codex.cmd"):
            with patch.object(self.agent.subprocess, "run",
                              side_effect=__import__("subprocess").TimeoutExpired("codex", 10)):
                self.assertFalse(self.agent.probe_capabilities()["codex_authenticated"])

    def test_once_initial_heartbeat_is_synchronous(self):
        import inspect
        source = inspect.getsource(self.agent.main)
        self.assertLess(source.index("send_heartbeat(base, agent_id, projects, capabilities, token)"),
                        source.index("presence_thread.start()"))
        self.assertIn("heartbeat_interval = min(interval, 15)", source)

    def test_heartbeat_only_sends_allowlisted_metadata(self):
        with patch.object(self.agent, "post_json", return_value={"ok": True}) as send:
            self.assertTrue(self.agent.send_heartbeat(
                "http://127.0.0.1:8001", "win-01", ["LKH_MCP"], CAPS, "private"))
            payload = send.call_args.args[2]
            self.assertEqual(set(payload), {"agent_id", "projects", "capabilities"})
            self.assertNotIn("private", str(payload))
            self.assertEqual(send.call_args.args[1], "/admin/agent/heartbeat")


if __name__ == "__main__":
    unittest.main()
