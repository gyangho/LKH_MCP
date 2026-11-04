"""Session/CSRF protected repository approvals."""
import json
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from admin_auth import AdminNotConfigured, AdminUnauthorized, valid_csrf
from admin_console import _verify_access, _private, _auth_response
import repository_store as store


def register_repository_routes(mcp):
    async def handle(request):
        try:
            actor = _verify_access(request)
            ident = request.path_params.get("ident")
            if request.method == "GET":
                from public_skills import skill_paths
                versions = {}
                for name in ("uiux", "graphify"):
                    component = skill_paths(name)
                    versions[name] = {"ready": component is not None,
                                      "version": component["version"] if component else None,
                                      "commit": component["commit"] if component else None}
                return _private(JSONResponse({"repositories": await run_in_threadpool(store.list_repositories),
                                              "public_skills": versions}))
            if not valid_csrf(request):
                return _private(JSONResponse({"error": "Origin / CSRF check failed"}, status_code=403))
            raw = await request.body()
            if not 1 <= len(raw) <= 2048:
                return _private(JSONResponse({"error": "Invalid payload length"}, status_code=413))
            data = json.loads(raw)
            if request.url.path.endswith("/test"):
                if not isinstance(data, dict) or set(data) != {"revision"}:
                    raise ValueError("Invalid check request")
                from repository_bindings import request_check
                result = await run_in_threadpool(request_check, ident, data["revision"], actor)
                return _private(JSONResponse(result, status_code=202))
            fields = {"revision"} if request.method == "DELETE" else {"alias", "repository"} | ({"revision"} if ident else set())
            if request.method != "DELETE":
                fields |= {"agent_id", "local_path"}
            if not isinstance(data, dict) or set(data) != fields: raise ValueError("Invalid fields")
            if request.method != "DELETE" and (not data["agent_id"] or not data["local_path"]):
                raise ValueError("Agent and local path required")
            if request.method == "DELETE":
                result = await run_in_threadpool(store.delete, ident, data["revision"], actor)
            elif ident:
                result = await run_in_threadpool(store.update, ident, data["revision"], data["alias"], data["repository"], actor, data["agent_id"], data["local_path"])
            else:
                result = await run_in_threadpool(store.create, data["alias"], data["repository"], actor, data["agent_id"], data["local_path"])
            return _private(JSONResponse(result, status_code=201 if request.method == "POST" else 200))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except PermissionError:
            return _private(JSONResponse({"error": "관리자 설정에서 Codex Agent를 활성화하세요."}, status_code=403))
        except store.NotFound:
            return _private(JSONResponse({"error": "승인 저장소를 찾을 수 없습니다."}, status_code=404))
        except store.Conflict:
            return _private(JSONResponse({"error": "변경 충돌: 별칭 중복·최대 10개·실행 중 작업·연결 확인·revision을 확인하고 새로고침하세요."}, status_code=409))
        except (ValueError, TypeError, KeyError, UnicodeDecodeError):
            return _private(JSONResponse({"error": "프로젝트 별칭, owner/repository, Agent ID 및 로컬 Windows 절대 경로를 확인하세요."}, status_code=400))
        except Exception:
            return _private(JSONResponse({"error": "승인 저장소를 저장하거나 읽을 수 없습니다."}, status_code=503))

    mcp.custom_route("/admin/api/repositories", methods=["GET", "POST"])(handle)
    mcp.custom_route("/admin/api/repositories/{ident}", methods=["PUT", "DELETE"])(handle)

    mcp.custom_route("/admin/api/repositories/{ident}/test", methods=["POST"])(handle)
