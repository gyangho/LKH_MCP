"""Installer settings survive restart and control real MCP Host validation."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_network as network
import native_runtime


class NetworkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "state"

    def test_saved_settings_reach_server_and_tray(self):
        network.save("192.0.1.22", "19000", "19001", root=self.root)
        env = {}
        native_runtime.prepare_native_environment(env, root=self.root)
        self.assertEqual((env["MCP_HOST"], env["MCP_PORT"], env["LKH_NATIVE_ADMIN_PORT"]),
                         ("192.0.1.22", "19000", "19001"))
        with patch.dict(os.environ, {"LKH_NATIVE_STATE_DIR": str(self.root), "LKH_NATIVE_ADMIN_PORT": ""}):
            from native_tray import _admin_base
            self.assertEqual(_admin_base(), "http://127.0.0.1:19001")

    def test_invalid_input_preserves_existing_settings(self):
        network.save("192.0.1.22", "8000", "8001", root=self.root)
        original = network.config_path(self.root).read_bytes()
        invalid = ([(host, "8000", "8001") for host in
                     ("0.0.0.0", "224.1.1.1", "255.255.255.255", "example.com", "192.0.1.999", "1.2.3.4\nother=1")]
                    + [("127.0.0.1", port, "8001") for port in
                       ("0", "65536", "-1", "8001", "8000;evil", "８０００")])
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValueError):
                network.save(*args, root=self.root)
            self.assertEqual(network.config_path(self.root).read_bytes(), original)

    def test_corrupt_file_fails_closed_before_creating_runtime_directories(self):
        path = network.config_path(self.root)
        path.parent.mkdir(parents=True)
        path.write_text("[network]\nhost=0.0.0.0\nmcp_port=8000\nadmin_port=8001\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            native_runtime.prepare_native_environment({}, root=self.root)
        self.assertFalse((self.root / "data").exists())

    def test_native_origin_follows_admin_port_and_preserves_credentials(self):
        import settings_store
        network.save("192.0.1.22", "19000", "19001", root=self.root)
        bootstrap = self.root / "config/bootstrap.json"
        original = json.dumps({"ADMIN_LOGIN_USER": "existing-admin", "ADMIN_PUBLIC_ORIGIN": "http://127.0.0.1:8001"})
        bootstrap.write_text(original, encoding="utf-8")
        with patch.dict(os.environ, {"LKH_NATIVE_STATE_DIR": str(self.root)}, clear=True), \
                patch.object(settings_store, "_READY", False):
            native_runtime.prepare_native_environment()
            settings_store.initialize()
            self.assertEqual(os.environ["ADMIN_PUBLIC_ORIGIN"], "http://127.0.0.1:19001")
            self.assertEqual(os.environ["ADMIN_LOGIN_USER"], "existing-admin")
        self.assertEqual(bootstrap.read_text("utf-8"), original)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_ip_accepted_and_unrelated_host_and_origin_rejected(self):
        import httpx
        from mcp.server import MCPServer
        from native_gateway import SurfaceGuard, transport_security
        server = MCPServer("network-test")
        app = server.streamable_http_app(stateless_http=True, json_response=True,
            transport_security=transport_security("192.0.1.22", 19000))
        async with server.session_manager.run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=SurfaceGuard(app, "mcp")),
                                         base_url="http://192.0.1.22:19000") as client:
                headers = {"Accept": "application/json, text/event-stream"}
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
                response = await client.post("/mcp", json=body, headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertIn("result", response.json())
                response = await client.post("/mcp", json=body, headers={**headers, "Host": "evil.example"})
                self.assertEqual(response.status_code, 421)
                response = await client.post("/mcp", json=body, headers={**headers, "Origin": "http://evil.example"})
                self.assertEqual(response.status_code, 403)
                self.assertEqual((await client.get("/admin/healthz")).status_code, 404)

    async def test_admin_listener_remains_loopback(self):
        import uvicorn
        from mcp.server import MCPServer
        from native_gateway import run_native_gateways
        configs = []
        class FakeServer:
            def __init__(self, config):
                configs.append(config)
            async def serve(self):
                return
        with patch.object(uvicorn, "Server", FakeServer):
            await run_native_gateways(MCPServer("test"), host="192.0.1.22", mcp_port=19000, admin_port=19001)
        self.assertEqual([(c.host, c.port) for c in configs], [("192.0.1.22", 19000), ("127.0.0.1", 19001)])
