"""ASGI route separation for the two native Windows HTTP listeners."""
from __future__ import annotations

MCP_ROUTES = frozenset(("/mcp", "/mcp/"))


def allowed_path(surface: str, path: str) -> bool:
    if surface == "mcp":
        return path in MCP_ROUTES
    if surface == "admin":
        return path == "/admin" or path.startswith("/admin/")
    return False


class SurfaceGuard:
    def __init__(self, app, surface: str):
        if surface not in ("mcp", "admin"):
            raise ValueError("Invalid native gateway surface")
        self.app = app
        self.surface = surface

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "http" and self.surface == "admin" and scope.get("path") == "/admin/healthz":
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": b'{"status":"ok"}'})
            return
        if kind != "http" or not allowed_path(self.surface, scope.get("path", "")):
            if kind == "http":
                await send({"type": "http.response.start", "status": 404,
                            "headers": [(b"content-type", b"text/plain"),
                                        (b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": b"Not Found"})
            elif kind == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


async def run_native_gateways(mcp, *, host: str, mcp_port: int,
                              admin_port: int, stop_event=None) -> None:
    """Run one MCP manager behind two independently filtered HTTP listeners."""
    import asyncio
    import uvicorn
    backend = mcp.streamable_http_app(stateless_http=True, json_response=True)
    servers = [
        uvicorn.Server(uvicorn.Config(
            SurfaceGuard(backend, "mcp"), host=host, port=mcp_port,
            lifespan="off", access_log=False, log_level="warning")),
        uvicorn.Server(uvicorn.Config(
            SurfaceGuard(backend, "admin"), host=host, port=admin_port,
            lifespan="off", access_log=False, log_level="warning")),
    ]
    async with mcp.session_manager.run():
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        stop_task = (asyncio.create_task(stop_event.wait())
                     if stop_event is not None else None)
        try:
            pending = set(tasks)
            if stop_task is not None:
                pending.add(stop_task)
            done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is not stop_task:
                    await task
        finally:
            for server in servers:
                server.should_exit = True
            if stop_task:
                stop_task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
