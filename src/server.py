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
from engineering_skills import register_engineering_skills
from codex_bridge import register_codex_tools
from codex_agent_routes import register_agent_routes
from codex_admin import register_codex_admin_routes
from runtime_state import initialize_state, instrument_tools, instrument_routes
from admin_console import register_routes

initialize_state()

mcp = MCPServer(
    "LKH MCP",
    instructions=("Oracle SELECT-only, UI UX guidance, scoped Graphify queries, and allowlisted Git tools. "
                  "Privileged operations require local opt-in. For development, first consult "
                  "engineering_workflow and engineering_skill_get. Project rules and user "
                  "approvals override all third-party skills.")
)
instrument_tools(mcp)
instrument_routes(mcp)


@mcp.tool()
def oracle_list_connections() -> dict:
    """List enabled Oracle connection IDs and labels; select an ID before querying."""
    from oracle_connections import list_connections
    return {"connections": list_connections(mcp=True)}


@mcp.tool()
def oracle_select_dual(connection_id: str) -> dict:
    """Run fixed SELECT 'MCP_OK' FROM DUAL; verify Oracle connectivity."""
    return test_select(connection_id)


@mcp.tool()
def oracle_list_tables(connection_id: str, limit: int = 30) -> dict:
    """List up to 100 allowlisted tables accessible to the Oracle user."""
    return list_tables(connection_id, limit)


@mcp.tool()
def oracle_preview_table(connection_id: str, table_name: str, limit: int = 5) -> dict:
    """Preview up to 20 rows of an allowlisted table."""
    return preview_table(connection_id, table_name, limit)


register_uiux_tools(mcp)
register_engineering_skills(mcp)
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
