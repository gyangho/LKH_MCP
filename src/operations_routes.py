"""Private, session/CSRF-protected operations log and metric APIs."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from admin_auth import AdminNotConfigured, AdminUnauthorized
from admin_console import _verify_access, _auth_response, _private
from runtime_state import telemetry
import operations_store


def register_operations_routes(mcp):
    @mcp.custom_route("/admin/operations", methods=["GET"])
    async def html_page(request: Request):
        from starlette.responses import HTMLResponse
        from admin_console import _html
        try:
            _verify_access(request)
            return _private(HTMLResponse(_html()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/operations/logs", methods=["GET"])
    async def logs(request: Request):
        try:
            _verify_access(request)
            cursor = int(request.query_params.get("cursor", "0"))
            category = request.query_params.get("category", "")
            return _private(JSONResponse(
                operations_store.read_events(cursor=cursor, category=category)))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except ValueError:
            return _private(JSONResponse({"error": "invalid log query"}, status_code=400))

    @mcp.custom_route("/admin/api/operations/metrics", methods=["GET"])
    async def metrics(request: Request):
        try:
            _verify_access(request)
            minutes = int(request.query_params.get("minutes", "60"))
            result = operations_store.metrics(minutes)
            state = telemetry()
            result["runtime"] = {"cpu_percent": state["cpu_percent"],
                                 "memory_mb": state["memory_mb"],
                                 "threads": state["threads"],
                                 "uptime_seconds": state["uptime_seconds"],
                                 "requests": state["requests"]}
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except ValueError:
            return _private(JSONResponse({"error": "invalid metrics query"}, status_code=400))
