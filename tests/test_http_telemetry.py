"""Phase 7 API latency/status is logged without request headers, URLs or bodies."""
import types
import unittest
from unittest.mock import patch

import runtime_state


class FakeMCP:
    def __init__(self):
        self.routes = {}
    def custom_route(self, path, methods):
        def add(fn):
            self.routes[path] = fn
            return fn
        return add


class HttpTelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_route_status_and_metadata_only(self):
        mcp = FakeMCP()
        runtime_state.instrument_routes(mcp)

        @mcp.custom_route("/admin/api/example", methods=["GET"])
        async def example(request):
            return types.SimpleNamespace(status_code=401, headers={})

        request = types.SimpleNamespace(
            headers={"authorization": "Bearer PRIVATE"},
            url="https://internal.example/admin/api/example?secret=PRIVATE",
            body="PRIVATE",
        )
        with patch.object(runtime_state, "_record") as recorded:
            result = await mcp.routes["/admin/api/example"](request)
            self.assertEqual(result.status_code, 401)
            self.assertEqual(len(result.headers["X-Correlation-ID"]), 32)
        args, kw = recorded.call_args
        self.assertEqual(args, ("api_example", "error"))
        self.assertTrue(0 <= kw["duration_ms"] <= 3600000)
        self.assertNotIn("PRIVATE", repr(recorded.call_args))


if __name__ == "__main__":
    unittest.main()
