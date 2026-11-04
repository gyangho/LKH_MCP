"""LKH MCP 0.0.1: Oracle, UI UX Pro Max, Graphify, Git, and admin console.

Expose /mcp ONLY behind the existing Cloudflare MCP Portal/Access controls.
Dashboard admin routes use private administrator sessions, with WARP Access/Gateway as network layer.
"""
import os
import settings_store
settings_store.initialize()
from mcp.server import MCPServer
from oracle_db import test_select, list_tables, preview_table
from uiux_tools import register_uiux_tools
from codex_bridge import register_codex_tools
from codex_agent_routes import register_agent_routes
from codex_admin import register_codex_admin_routes
from runtime_state import initialize_state, instrument_tools, instrument_routes
from admin_console import register_routes

initialize_state()

mcp = MCPServer(
    "LKH MCP",
    instructions="Oracle SELECT-only, UI UX guidance, scoped Graphify queries, and allowlisted Git tools. Privileged operations require local opt-in. For every Oracle request, use the connection name explicitly selected by the user. If none is specified in context, ask which connection to use; never choose one automatically. Resolve names with oracle_list_connections or connection_name."
)
instrument_tools(mcp)
instrument_routes(mcp)


def _oracle_call(query, connection_id, connection_name, *args):
    from oracle_connections import resolve_connection, NotFound
    from oracle_db import OracleUnavailable
    try:
        ident = resolve_connection(name=connection_name, connection_id=connection_id)
    except (ValueError, NotFound):
        return {"error": {"code": "CONNECTION_SELECTION_REQUIRED",
                          "message": "사용할 연결 이름 하나를 확인하세요. 없거나 중복된 이름은 연결 목록에서 선택하세요."}}
    try:
        return query(ident, *args)
    except OracleUnavailable as exc:
        return {"error": {"code": "ORACLE_UNAVAILABLE", "message": str(exc)}}


@mcp.tool()
def oracle_list_connections() -> dict:
    """List enabled Oracle connection IDs and labels; select an ID before querying."""
    from oracle_connections import list_connections
    return {"connections": list_connections(mcp=True)}


@mcp.tool()
def oracle_select_dual(connection_id: str = "", connection_name: str = "") -> dict:
    """Run fixed SELECT 'MCP_OK' FROM DUAL; verify Oracle connectivity. Specify connection_name or connection_id; ask the user if neither is known."""
    return _oracle_call(test_select, connection_id, connection_name)


@mcp.tool()
def oracle_list_tables(connection_id: str = "", limit: int = 30, connection_name: str = "") -> dict:
    """List up to 100 allowlisted tables accessible to the Oracle user."""
    return _oracle_call(list_tables, connection_id, connection_name, limit)


@mcp.tool()
def oracle_preview_table(connection_id: str = "", table_name: str = "", limit: int = 5, connection_name: str = "") -> dict:
    """Preview up to 20 rows of an allowlisted table."""
    return _oracle_call(preview_table, connection_id, connection_name, table_name, limit)


register_uiux_tools(mcp)
register_codex_tools(mcp)
register_agent_routes(mcp)
register_codex_admin_routes(mcp)
from instruction_routes import register_instruction_tools, register_instruction_admin
register_instruction_tools(mcp)
register_instruction_admin(mcp)
from operations_routes import register_operations_routes
register_operations_routes(mcp)
register_routes(mcp)
from oracle_routes import register_oracle_routes
register_oracle_routes(mcp)
from repository_routes import register_repository_routes
register_repository_routes(mcp)

# Native-only privileged APIs, never registered in the Docker deployment.
if os.getenv("LKH_NATIVE_MODE") == "1":
    from native_host_routes import register_native_host_routes
    from native_enrollment_routes import register_native_enrollment_routes
    register_native_host_routes(mcp)
    register_native_enrollment_routes(mcp)


def run() -> None:
    mcp.run(
        transport="streamable-http",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    run()
