"""Codex Agent credential issuance, persistence, revocation, and local discovery."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
import codex_credentials as creds
import codex_bridge as bridge
import codex_admin
from windows_agent import agent


class TokenTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "mcp.sqlite3"
        for p in (
            patch.object(creds.settings_store, "_connect",
                         side_effect=lambda: sqlite3.connect(self.db)),
            patch.dict(os.environ, {"CODEX_AGENT_TOKEN": "L" * 48}),
        ):
            p.start()
            self.addCleanup(p.stop)

    def test_legacy_until_first_issuance_then_sticky_rotation(self):
        self.assertEqual(creds.status()["source"], "bootstrap")
        self.assertTrue(bridge.check_agent_token("Bearer " + "L" * 48))
        first = creds.rotate("admin")
        self.assertEqual(len(first["token"]), 64)
        self.assertEqual(first["status"]["source"], "managed")
        self.assertNotIn("token", creds.status())
        self.assertFalse(bridge.check_agent_token("Bearer " + "L" * 48))
        self.assertTrue(bridge.check_agent_token("Bearer " + first["token"]))
        # An independent database connection sees the same persistent verifier.
        self.assertEqual(creds.status()["source"], "managed")
        self.assertNotIn(first["token"], self.db.read_bytes().decode("latin-1"))
        second = creds.rotate("admin")
        self.assertNotEqual(first["token"], second["token"])
        self.assertFalse(bridge.check_agent_token("Bearer " + first["token"]))
        self.assertTrue(bridge.check_agent_token("Bearer " + second["token"]))

    def test_revoke_prevents_bootstrap_fallback_after_restart(self):
        token = creds.rotate("admin")["token"]
        self.assertTrue(creds.check_token("Bearer " + token))
        creds.revoke("admin")
        self.assertEqual(creds.status()["source"], "revoked")
        self.assertFalse(creds.status()["configured"])
        self.assertFalse(creds.check_token("Bearer " + token))
        self.assertFalse(creds.check_token("Bearer " + "L" * 48))
        self.assertFalse(creds.status()["configured"])

    def test_revoke_before_first_issuance_disables_legacy(self):
        creds.revoke("admin")
        self.assertFalse(creds.check_token("Bearer " + "L" * 48))

    def test_invalid_inputs_are_denied(self):
        for header in ("", "Bearer ", "Bearer " + "a" * 300,
                       "Basic " + "L" * 48, "Bearer " + "é" * 48):
            with self.subTest(header=header[:20]):
                self.assertFalse(creds.check_token(header))
        with self.assertRaises(ValueError):
            creds.rotate("")
        self.assertEqual(creds.status()["source"], "bootstrap")


class AutoLoadTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.agentdir = self.root / "windows_agent"
        self.agentdir.mkdir()
        self.cfg = self.agentdir / "config.json"
        self.cfg.write_text("{}", encoding="utf-8")
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.agentfile = patch.object(agent, "__file__", str(self.agentdir / "agent.py"))
        self.agentfile.start()
        self.addCleanup(self.agentfile.stop)

    def test_loads_private_token_file(self):
        (self.agentdir / "token.json").write_text(
            json.dumps({"token": "T" * 48}), encoding="utf-8")
        self.assertEqual(agent.load_agent_token(self.cfg), "T" * 48)

    def test_environment_precedes_file(self):
        (self.agentdir / "token.json").write_text(
            json.dumps({"token": "F" * 48}), encoding="utf-8")
        with patch.dict(os.environ, {"LKH_CODEX_AGENT_TOKEN": "E" * 48}):
            self.assertEqual(agent.load_agent_token(self.cfg), "E" * 48)

    def test_local_legacy_bootstrap_fallback(self):
        secret_dir = self.root / "secrets"
        secret_dir.mkdir()
        (secret_dir / "bootstrap.json").write_text(
            json.dumps({"CODEX_AGENT_TOKEN": "B" * 48,
                        "ADMIN_PASSWORD_HASH": "not-exposed"}), encoding="utf-8")
        self.assertEqual(agent.load_agent_token(self.cfg), "B" * 48)

    def test_malformed_private_file_fails_closed(self):
        (self.agentdir / "token.json").write_text(
            '{"token":"short"}', encoding="utf-8")
        with self.assertRaises(RuntimeError):
            agent.load_agent_token(self.cfg)

    def test_missing_token_is_error(self):
        with self.assertRaisesRegex(RuntimeError, "missing/invalid"):
            agent.load_agent_token(self.cfg)


class TokenRouteTests(unittest.IsolatedAsyncioTestCase):
    class FakeMCP:
        def __init__(self):
            self.routes = {}
        def custom_route(self, path, methods):
            def register(fn):
                self.routes[path] = fn
                return fn
            return register

    def request(self, method="POST", body=b'{"confirm":"ROTATE"}'):
        from starlette.requests import Request
        scope = {"type": "http", "http_version": "1.1", "method": method,
                 "scheme": "http", "path": "/admin/api/codex/token/rotate",
                 "root_path": "", "query_string": b"", "headers": []}
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}
        return Request(scope, receive)

    async def test_requires_admin_session(self):
        app = self.FakeMCP()
        codex_admin.register_codex_admin_routes(app)
        route = app.routes["/admin/api/codex/token/rotate"]
        with patch.object(codex_admin, "_verify_access",
                          side_effect=codex_admin.AdminUnauthorized):
            response = await route(self.request())
            self.assertEqual(response.status_code, 401)

    async def test_csrf_and_confirmation_required(self):
        app = self.FakeMCP()
        codex_admin.register_codex_admin_routes(app)
        route = app.routes["/admin/api/codex/token/rotate"]
        with patch.object(codex_admin, "_verify_access", return_value="admin"):
            with patch.object(codex_admin, "valid_csrf", return_value=False):
                self.assertEqual((await route(self.request())).status_code, 403)
            with patch.object(codex_admin, "valid_csrf", return_value=True):
                self.assertEqual((await route(self.request(body=b'{"confirm":"NO"}'))).status_code, 400)
                with patch.object(codex_admin.codex_credentials, "rotate",
                                  return_value={"token": "T" * 64, "status": {}}) as issue:
                    response = await route(self.request())
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(json.loads(response.body)["token"], "T" * 64)
                    self.assertEqual(response.headers.get("cache-control"), "no-store")
                    issue.assert_called_once_with("admin")


if __name__ == "__main__":
    unittest.main()
