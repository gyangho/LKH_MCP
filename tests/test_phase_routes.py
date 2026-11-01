"""Private routes fail closed; Phase 1 lease and Phase 6 CSRF contracts."""
import asyncio
import json
import unittest
from unittest.mock import patch

from starlette.requests import Request

import codex_agent_routes
import codex_admin
import instruction_routes
import operations_routes
from admin_auth import AdminUnauthorized


class FakeMCP:
    def __init__(self):
        self.routes = {}
    def custom_route(self, path, methods):
        def register(fn):
            self.routes[(path, tuple(methods))] = fn
            return fn
        return register


def req(path: str, method="GET", body=b"", *, params=None):
    raw_headers = [(b"content-type", b"application/json"),
                   (b"host", b"127.0.0.1:8001")]
    scope = {"type": "http", "path": path, "method": method,
             "scheme": "http", "query_string": b"",
             "headers": raw_headers, "path_params": params or {}}
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    return Request(scope, receive)


class RouteSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_instruction_mutation_requires_login(self):
        mcp = FakeMCP()
        instruction_routes.register_instruction_admin(mcp)
        endpoint = mcp.routes[("/admin/api/instructions", ("POST",))]
        with patch.object(instruction_routes, "_verify_access",
                          side_effect=AdminUnauthorized("denied")):
            result = await endpoint(req("/admin/api/instructions", "POST", b'{}'))
        self.assertEqual(result.status_code, 401)

    async def test_instruction_mutation_denies_csrf(self):
        mcp = FakeMCP()
        instruction_routes.register_instruction_admin(mcp)
        endpoint = mcp.routes[("/admin/api/instructions", ("POST",))]
        with patch.object(instruction_routes, "_verify_access", return_value="admin"), \
             patch.object(instruction_routes, "valid_csrf", return_value=False):
            result = await endpoint(req("/admin/api/instructions", "POST", b'{}'))
        self.assertEqual(result.status_code, 403)

    async def test_operations_read_requires_session(self):
        mcp = FakeMCP()
        operations_routes.register_operations_routes(mcp)
        endpoint = mcp.routes[("/admin/api/operations/logs", ("GET",))]
        with patch.object(operations_routes, "_verify_access",
                          side_effect=AdminUnauthorized("denied")):
            result = await endpoint(req("/admin/api/operations/logs"))
        self.assertEqual(result.status_code, 401)

    async def test_agent_events_token_and_lease_rejection(self):
        mcp = FakeMCP()
        codex_agent_routes.register_agent_routes(mcp)
        endpoint = mcp.routes[("/admin/agent/events", ("POST",))]
        payload = json.dumps({"task_id": "a"*32, "lease": "b"*64,
                              "agent_id": "win-dev-01", "events": [
                                  {"seq":1,"type":"started","phase":"codex"}
                              ]}).encode()
        with patch.object(codex_agent_routes, "check_agent_token", return_value=False):
            result = await endpoint(req("/admin/agent/events", "POST", payload))
            self.assertEqual(result.status_code, 401)
        with patch.object(codex_agent_routes, "check_agent_token", return_value=True), \
             patch("codex_events.append", side_effect=PermissionError("lease")):
            result = await endpoint(req("/admin/agent/events", "POST", payload))
            self.assertEqual(result.status_code, 403)

    async def test_event_timeline_requires_login(self):
        mcp = FakeMCP()
        codex_admin.register_codex_admin_routes(mcp)
        endpoint = mcp.routes[("/admin/api/codex/events/{task_id}", ("GET",))]
        with patch.object(codex_admin, "_verify_access",
                          side_effect=AdminUnauthorized("denied")):
            result = await endpoint(req("/admin/api/codex/events/a", params={"task_id":"a"*32}))
        self.assertEqual(result.status_code, 401)


if __name__ == "__main__":
    unittest.main()
