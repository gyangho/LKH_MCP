"""Private Oracle profile management. All writes/tests require session and CSRF."""
from __future__ import annotations

import json
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse

from admin_auth import AdminNotConfigured, AdminUnauthorized, valid_csrf
from admin_console import _verify_access, _auth_response, _private, _html
import oracle_connections as store
import oracle_db


def register_oracle_routes(mcp):
    @mcp.custom_route("/admin/oracle", methods=["GET"])
    async def page(request):
        try:
            _verify_access(request)
            return _private(HTMLResponse(_html()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    async def handle(request):
        try:
            actor = _verify_access(request)
            method = request.method
            ident = request.path_params.get("ident")
            if method == "GET":
                result = await run_in_threadpool(store.list_connections)
                return _private(JSONResponse({"connections": result}))
            if not valid_csrf(request):
                return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
            raw = await request.body()
            if not 1 <= len(raw) <= 12000:
                return _private(JSONResponse({"error": "Invalid payload length"}, status_code=413))
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Invalid payload")
            if request.url.path.endswith("/test"):
                if data:
                    raise ValueError("Test accepts an empty object")
                await run_in_threadpool(oracle_db.test_select, ident, allow_disabled=True)
                return _private(JSONResponse({"ok": True}))
            if method == "DELETE":
                if set(data) != {"revision"}:
                    raise ValueError("Invalid deletion")
                result = await run_in_threadpool(store.delete, ident, data["revision"], actor)
            else:
                expected = store.FIELDS | {"password"} | ({"revision"} if method == "PUT" else set())
                if set(data) != expected:
                    raise ValueError("Invalid profile fields")
                profile = {key: data[key] for key in store.FIELDS}
                if method == "PUT":
                    result = await run_in_threadpool(store.update, ident, data["revision"], profile, data["password"], actor)
                else:
                    result = await run_in_threadpool(store.create, profile, data["password"], actor)
            return _private(JSONResponse(result, status_code=201 if method == "POST" else 200))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except oracle_db.OracleUnavailable as exc:
            return _private(JSONResponse({"error": str(exc)}, status_code=503))
        except store.NotFound:
            return _private(JSONResponse({"error": "Oracle 연결을 찾을 수 없습니다."}, status_code=404))
        except store.Conflict:
            return _private(JSONResponse({"error": "다른 관리자가 수정했습니다. 새로고침 후 다시 시도하세요."}, status_code=409))
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            return _private(JSONResponse({"error": "연결 항목과 형식을 확인하세요. 이름·사용자·암호 및 Service/SID가 필요합니다."}, status_code=400))
        except Exception:
            # Never return driver/DPAPI/database error contents.
            return _private(JSONResponse({"error": "Oracle 처리 실패: 연결 설정과 Windows 자격증명 보호 상태를 확인하세요."}, status_code=503))

    mcp.custom_route("/admin/api/oracle/connections", methods=["GET", "POST"])(handle)
    mcp.custom_route("/admin/api/oracle/connections/{ident}", methods=["PUT", "DELETE"])(handle)
    mcp.custom_route("/admin/api/oracle/connections/{ident}/test", methods=["POST"])(handle)
