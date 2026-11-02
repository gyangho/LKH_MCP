"""Test MCP discovery + oracle_select_dual via local Streamable HTTP."""
import asyncio


async def main():
    from mcp import Client
    async with Client("http://127.0.0.1:8000/mcp") as client:
        result = await client.list_tools()
        names = [t.name for t in result.tools]
        print("MCP_TOOLS:", names)
        if "oracle_select_dual" not in names:
            raise RuntimeError("oracle_select_dual tool not exposed")
        import os
        connection_id = os.environ["LKH_TEST_ORACLE_CONNECTION_ID"]
        response = await client.call_tool("oracle_select_dual", {"connection_id": connection_id})
        print("MCP_SELECT_RESPONSE:", response)
        if response.isError:
            raise RuntimeError("MCP tool reported an Oracle error")


if __name__ == "__main__":
    asyncio.run(main())
