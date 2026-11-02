"""Private profile API contracts; Oracle I/O is mocked, auth/CSRF are exercised."""
import asyncio
import json
import os
import unittest
from unittest.mock import patch

from starlette.requests import Request
import oracle_routes
import admin_auth
from tests.test_admin_console import FakeMCP


class RouteTests(unittest.TestCase):
    def setUp(self):
        mcp = FakeMCP()
        oracle_routes.register_oracle_routes(mcp)
        self.routes = mcp.routes

    def invoke(self, method="POST", body=None, ident=None, testing=False, headers=None):
        route = "/admin/api/oracle/connections" + ("/{ident}" if ident else "") + ("/test" if testing else "")
        path = route.replace("{ident}", ident or "")
        methods = ("GET", "POST") if not ident else (("POST",) if testing else ("PUT", "DELETE"))
        raw = json.dumps({} if body is None else body).encode()
        async def receive(): return {"type": "http.request", "body": raw, "more_body": False}
        req = Request({"type": "http", "method": method, "path": path, "path_params": {"ident": ident} if ident else {},
                       "headers": [(k.encode(), v.encode()) for k,v in (headers or {}).items()],
                       "query_string": b"", "scheme": "http", "server": ("127.0.0.1", 8001)}, receive)
        return asyncio.run(self.routes[(route, methods)](req))

    def test_get_requires_authentication(self):
        with patch.object(oracle_routes, "_verify_access", side_effect=admin_auth.AdminUnauthorized()):
            self.assertEqual(self.invoke("GET").status_code, 401)

    def test_mutations_and_connection_test_require_csrf(self):
        with patch.object(oracle_routes, "_verify_access", return_value="admin"), patch.object(oracle_routes, "valid_csrf", return_value=False):
            for method, ident, testing in (("POST", None, False), ("PUT", "db-id", False), ("DELETE", "db-id", False), ("POST", "db-id", True)):
                self.assertEqual(self.invoke(method, ident=ident, testing=testing).status_code, 403)

    def test_unknown_fields_rejected_before_storage(self):
        with patch.object(oracle_routes, "_verify_access", return_value="admin"), patch.object(oracle_routes, "valid_csrf", return_value=True), patch.object(oracle_routes.store, "create") as create:
            self.assertEqual(self.invoke(body={"arbitrary": "value"}).status_code, 400)
            create.assert_not_called()

    def test_secret_errors_redacted(self):
        with patch.object(oracle_routes, "_verify_access", return_value="admin"), patch.object(oracle_routes, "valid_csrf", return_value=True), patch.object(oracle_routes.oracle_db, "test_select", side_effect=RuntimeError("password=private-secret")):
            result = self.invoke(ident="db-id", testing=True)
            self.assertEqual(result.status_code, 503)
            self.assertNotIn(b"private-secret", result.body)
            self.assertEqual(result.headers["cache-control"], "no-store")

    def test_revision_conflict_is_409(self):
        with patch.object(oracle_routes, "_verify_access", return_value="admin"), patch.object(oracle_routes, "valid_csrf", return_value=True), patch.object(oracle_routes.store, "delete", side_effect=oracle_routes.store.Conflict()):
            self.assertEqual(self.invoke("DELETE", {"revision": 1}, "db-id").status_code, 409)

    def test_enabled_profile_test_runs_with_explicit_id(self):
        with patch.object(oracle_routes, "_verify_access", return_value="admin"), patch.object(oracle_routes, "valid_csrf", return_value=True), patch.object(oracle_routes.oracle_db, "test_select", return_value={"status": "MCP_OK"}) as select:
            self.assertEqual(json.loads(self.invoke(ident="db-id", testing=True).body), {"ok": True})
            select.assert_called_once_with("db-id", allow_disabled=True)

if __name__ == "__main__": unittest.main()
