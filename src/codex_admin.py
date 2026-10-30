"""Private administrator approval for Windows Codex tasks; no local patch application."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from admin_console import (_verify_access, _auth_response, _private,
                           AdminNotConfigured, AdminUnauthorized)
from admin_auth import valid_csrf
from codex_bridge import decide, list_tasks


def register_codex_admin_routes(mcp):
    @mcp.custom_route('/admin/codex', methods=['GET'])
    async def page(request: Request):
        try:
            _verify_access(request)
            base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
            return _private(HTMLResponse((base / 'web' / 'dist' / 'index.html').read_text(encoding='utf-8')))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route('/admin/api/codex/tasks', methods=['GET'])
    async def tasks(request: Request):
        try:
            _verify_access(request)
            return _private(JSONResponse(list_tasks()))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))

    @mcp.custom_route('/admin/api/codex/decision', methods=['POST'])
    async def decision(request: Request):
        try:
            actor = _verify_access(request)
            if not valid_csrf(request):
                return _private(JSONResponse({'error': 'origin/CSRF check failed'}, status_code=403))
            body = await request.body()
            if not 1 <= len(body) <= 1000:
                return _private(JSONResponse({'error': 'invalid payload size'}, status_code=413))
            data = json.loads(body)
            if not isinstance(data, dict) or set(data) != {'task_id', 'action'}:
                raise ValueError('Unexpected fields')
            if data['action'] not in ('approve', 'reject', 'cancel'):
                raise ValueError('Unexpected action')
            result = decide(data['task_id'], data['action'], actor)
            return _private(JSONResponse(result))
        except (AdminNotConfigured, AdminUnauthorized) as exc:
            return _private(_auth_response(exc, request))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            return _private(JSONResponse({'error': 'invalid approval'}, status_code=400))
        except PermissionError:
            return _private(JSONResponse({'error': 'agent disabled or forbidden'}, status_code=403))
