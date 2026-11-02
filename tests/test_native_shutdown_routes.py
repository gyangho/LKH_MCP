"""Native-only authenticated shutdown endpoint; never modifies the host in tests."""
import json
import unittest
from unittest.mock import patch

from starlette.requests import Request
from admin_auth import AdminUnauthorized
import native_host_routes as host


class FakeMCP:
    def __init__(self):
        self.routes = {}

    def custom_route(self, path, methods):
        def register(fn):
            self.routes[(path, tuple(methods))] = fn
            return fn
        return register


def request(target: str, confirm: str):
    body = json.dumps({"confirm": confirm}).encode()
    scope = {"type": "http", "method": "POST", "path": "/admin/api/host/shutdown/" + target,
             "scheme": "http", "query_string": b"", "path_params": {"target": target},
             "headers": [(b"content-type", b"application/json"), (b"host", b"127.0.0.1:8001")]}
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    return Request(scope, receive)


class ShutdownSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app = FakeMCP()
        host.register_native_host_routes(app)
        self.endpoint = app.routes[("/admin/api/host/shutdown/{target}", ("POST",))]
        host._LAST_ACTION = 0.0

    async def test_docker_never_has_shutdown_control(self):
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "0"}):
            result = await self.endpoint(request("server", "STOP_SERVER"))
        self.assertEqual(result.status_code, 404)

    async def test_no_session_or_csrf_denied(self):
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}), \
             patch.object(host, "verify_admin_session", side_effect=AdminUnauthorized("denied")):
            result = await self.endpoint(request("server", "STOP_SERVER"))
        self.assertEqual(result.status_code, 401)
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}), \
             patch.object(host, "verify_admin_session", return_value="admin"), \
             patch.object(host, "valid_csrf", return_value=False):
            result = await self.endpoint(request("server", "STOP_SERVER"))
        self.assertEqual(result.status_code, 403)

    async def test_confirmation_mismatch_denied(self):
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}), \
             patch.object(host, "verify_admin_session", return_value="admin"), \
             patch.object(host, "valid_csrf", return_value=True):
            result = await self.endpoint(request("both", "STOP_SERVER"))
        self.assertEqual(result.status_code, 400)

    async def test_busy_agent_blocks_server_shutdown(self):
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}), \
             patch.object(host, "verify_admin_session", return_value="admin"), \
             patch.object(host, "valid_csrf", return_value=True), \
             patch.object(host, "agents_snapshot", return_value={"agents": [{"busy": True}]}), \
             patch("native_shutdown.schedule_shutdown") as shutdown:
            result = await self.endpoint(request("server", "STOP_SERVER"))
        self.assertEqual(result.status_code, 409)
        shutdown.assert_not_called()

    async def test_both_stops_agent_first_then_server(self):
        events = []
        with patch.dict("os.environ", {"LKH_NATIVE_MODE": "1"}), \
             patch.object(host, "verify_admin_session", return_value="admin"), \
             patch.object(host, "valid_csrf", return_value=True), \
             patch.object(host, "agents_snapshot", return_value={"agents": []}), \
             patch.object(host, "task_state", return_value="running"), \
             patch.object(host, "control_agent", side_effect=lambda *a, **kw: events.append("agent")), \
             patch("native_shutdown.schedule_shutdown", side_effect=lambda: events.append("server")), \
             patch("runtime_state._record"):
            result = await self.endpoint(request("both", "STOP_BOTH"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(events, ["agent", "server"])


if __name__ == "__main__":
    unittest.main()
