"""MCP server exposing safe Oracle SELECT tools.

Local-only starter. Do NOT expose this directly via a public tunnel until
MCP-compatible authentication and authorization are configured.
"""

import os
from mcp.server import MCPServer
from oracle_db import test_select, list_tables, preview_table
from uiux_tools import register_uiux_tools
from graphify_tools import register_graphify_tools
from git_tools import register_git_tools
from git_commit_tools import register_git_commit_tools

mcp = MCPServer(
    "Oracle Local Read-Only MCP",
    instructions="Safe Oracle SELECT tools, UI UX guidance, and allowlisted Graphify graph queries. No arbitrary SQL or shell execution; bounded local Git status/diff and opted-in staging, AI-reviewed Git commits and committed push."
)


@mcp.tool()
def oracle_select_dual() -> dict:
    """Run a fixed SELECT 'MCP_OK' FROM DUAL; verify Oracle connectivity."""
    return test_select()


@mcp.tool()
def oracle_list_tables(limit: int = 30) -> dict:
    """List up to 100 allowlisted table names accessible to the Oracle user."""
    return list_tables(limit)


@mcp.tool()
def oracle_preview_table(table_name: str, limit: int = 5) -> dict:
    """Preview up to 20 rows of an allowlisted TABLE or OWNER.TABLE accessible by this DB user."""
    return preview_table(table_name, limit)


register_uiux_tools(mcp)
register_graphify_tools(mcp)
register_git_tools(mcp)
register_git_commit_tools(mcp)

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
        stateless_http=True,
        json_response=True,
    )
