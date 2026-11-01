"""I1 dual-surface ASGI safety tests."""
import asyncio
import unittest

from native_gateway import SurfaceGuard, allowed_path


class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def _request(self, surface, path, kind="http"):
        calls = []
        async def backend(scope, receive, send):
            calls.append("backend")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        async def recv():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(data):
            calls.append(data)
        await SurfaceGuard(backend, surface)({"type": kind, "path": path}, recv, send)
        return calls

    async def test_mcp_port_does_not_expose_admin_or_health(self):
        for path in ("/admin", "/admin/api/config", "/admin/agent/claim",
                     "/admin/healthz", "/healthz", "/mcp-secret", "/"):
            with self.subTest(path=path):
                events = await self._request("mcp", path)
                self.assertEqual(events[0]["status"], 404)
                self.assertNotIn("backend", events)
        self.assertIn("backend", await self._request("mcp", "/mcp"))
        self.assertIn("backend", await self._request("mcp", "/mcp/"))

    async def test_admin_port_does_not_expose_mcp(self):
        for path in ("/mcp", "/mcp/", "/administer", "/healthz", "/"):
            with self.subTest(path=path):
                self.assertEqual((await self._request("admin", path))[0]["status"], 404)
        self.assertIn("backend", await self._request("admin", "/admin"))
        self.assertIn("backend", await self._request("admin", "/admin/api/codex/agents"))
        self.assertEqual((await self._request("admin", "/admin/healthz"))[0]["status"], 200)

    async def test_websockets_never_pass(self):
        for surface in ("mcp", "admin"):
            self.assertEqual((await self._request(surface, "/mcp", "websocket"))[0]["code"], 1008)

    def test_invalid_surface_rejected(self):
        with self.assertRaises(ValueError):
            SurfaceGuard(None, "all")


if __name__ == "__main__":
    unittest.main()
