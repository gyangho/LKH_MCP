"""Phase 5 MCP read-only instruction tools and Phase 6 private admin editor."""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from admin_auth import AdminNotConfigured, AdminUnauthorized, valid_csrf
from admin_console import _verify_access, _auth_response, _private
import instruction_store as store


def register_instruction_tools(mcp):
    @mcp.tool()
    def instructions_list() -> dict:
        """List published instruction scopes and versions (never drafts)."""
        return store.list_entries(published_only=True)

    @mcp.tool()
    def instructions_get(instruction_id: str) -> dict:
        """Read a published instruction by ID."""
        return store.get_entry(instruction_id, published_only=True)

    @mcp.tool()
    def instructions_resolve(name: str, project: str = "", agent: str = "", tool: str = "") -> dict:
        """Resolve published instruction with tool > agent > project > global precedence."""
        return store.resolve(name, project=project, agent=agent, tool=tool)


def register_instruction_admin(mcp):
    @mcp.custom_route("/admin/instructions", methods=["GET"])
    async def html_page(request: Request):
        from starlette.responses import HTMLResponse
        from admin_console import _html
        try:
            _verify_access(request)
            return _private(HTMLResponse(_html()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/instructions", methods=["GET"])
    async def entries(request: Request):
        try:
            _verify_access(request)
            return _private(JSONResponse(store.list_entries(published_only=False)))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route("/admin/api/instructions/{ident}/history", methods=["GET"])
    async def versions(request: Request):
        try:
            _verify_access(request)
            return _private(JSONResponse(store.history(request.path_params["ident"])))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except ValueError:
            return _private(JSONResponse({"error": "invalid instruction"}, status_code=404))

    @mcp.custom_route("/admin/api/instructions", methods=["POST"])
    async def edit(request: Request):
        try:
            actor = _verify_access(request)
            if not valid_csrf(request):
                return _private(JSONResponse({"error": "CSRF"}, status_code=403))
            raw = await request.body()
            if not 1 <= len(raw) <= 6500:
                raise ValueError("Invalid instruction payload length")
            import json
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {"action", "payload"}:
                raise ValueError("Invalid instruction payload")
            action, p = data["action"], data["payload"]
            if not isinstance(p, dict):
                raise ValueError("Invalid payload")
            contracts = {
                "create": {"name", "scope", "scope_key", "body"},
                "save": {"id", "revision", "body"},
                "publish": {"id", "revision"},
                "rollback": {"id", "revision", "target_revision"},
            }
            if action not in contracts or set(p) != contracts[action]:
                raise ValueError("Unsupported instruction action")
            if action == "create":
                result = store.create(p["name"], p["scope"], p["scope_key"], p["body"], actor)
            elif action == "save":
                result = store.save(p["id"], p["body"], p["revision"], actor)
            elif action == "publish":
                result = store.publish(p["id"], p["revision"], actor)
            else:
                result = store.rollback(p["id"], p["target_revision"], p["revision"], actor)
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except (ValueError, TypeError, KeyError):
            return _private(JSONResponse({"error": "invalid, duplicate or stale instruction"}, status_code=400))
        except __import__("sqlite3").IntegrityError:
            return _private(JSONResponse({"error": "instruction scope already exists"}, status_code=409))
