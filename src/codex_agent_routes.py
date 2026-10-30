"""Token-authenticated private Windows agent HTTP routes; never accesses source trees."""
from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from codex_bridge import check_agent_token, claim, complete


def register_agent_routes(mcp: Any) -> None:
    @mcp.custom_route("/admin/agent/claim", methods=["POST"])
    async def agent_claim(request: Request):
        if not check_agent_token(request.headers.get("authorization", "")):
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"Cache-Control": "no-store"})
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise ValueError("JSON required")
            raw = await request.body()
            if not 1 <= len(raw) <= 4096:
                raise ValueError("Invalid body length")
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {"agent_id", "projects"}:
                raise ValueError("Invalid claim")
            result = claim(data["agent_id"], data["projects"])
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except PermissionError:
            return JSONResponse({"error": "agent disabled"}, status_code=403)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JSONResponse({"error": "invalid claim"}, status_code=400)

    @mcp.custom_route("/admin/agent/complete", methods=["POST"])
    async def agent_complete(request: Request):
        if not check_agent_token(request.headers.get("authorization", "")):
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"Cache-Control": "no-store"})
        try:
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise ValueError("JSON required")
            length = int(request.headers.get("content-length", "0"))
            if not 1 <= length <= 5_600_000:
                return JSONResponse({"error": "invalid body size"}, status_code=413)
            raw = await request.body()
            if not 1 <= len(raw) <= 5_600_000:
                return JSONResponse({"error": "invalid body size"}, status_code=413)
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {
                "id", "lease", "agent_id", "success", "report", "error", "graph_base64"
            }:
                raise ValueError("Invalid result fields")
            result = complete(data["id"], data["lease"], data["agent_id"],
                              data["success"], data["report"], data["error"], data["graph_base64"])
            return JSONResponse(result, headers={"Cache-Control": "no-store"})
        except PermissionError:
            return JSONResponse({"error": "lease rejected or agent disabled"}, status_code=403)
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return JSONResponse({"error": "invalid result"}, status_code=400)
