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
from runtime_state import initialize_state, instrument_tools
from admin_console import register_routes

initialize_state()

mcp = MCPServer(
    "LKH MCP",
    instructions="Oracle SELECT-only, UI UX guidance, scoped Graphify queries, and allowlisted Git tools. Privileged operations require local opt-in."
)
instrument_tools(mcp)


@mcp.tool()
def oracle_select_dual() -> dict:
    """Run fixed SELECT 'MCP_OK' FROM DUAL; verify Oracle connectivity."""
    return test_select()


@mcp.tool()
def oracle_list_tables(limit: int = 30) -> dict:
    """List up to 100 allowlisted tables accessible to the Oracle user."""
    return list_tables(limit)


@mcp.tool()
def oracle_preview_table(table_name: str, limit: int = 5) -> dict:
    """Preview up to 20 rows of an allowlisted table."""
    return preview_table(table_name, limit)


register_uiux_tools(mcp)
register_codex_tools(mcp)
register_agent_routes(mcp)
register_codex_admin_routes(mcp)
register_routes(mcp)


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
