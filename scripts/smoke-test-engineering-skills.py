"""Smoke-test real MCP skill tools against the staged loopback server."""
import asyncio
import json
import os
from mcp import Client

EXPECTED = "4ae2317ddb22b046e26455e4f9c9b3aaaf62212d"


def unpack(response):
    if response.isError:
        raise RuntimeError("MCP tool call failed")
    for item in response.content:
        body = getattr(item, "text", None)
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                continue
    raise RuntimeError("MCP tool returned no JSON content")


async def main():
    endpoint = os.environ.get("LKH_SKILLS_MCP_SMOKE_URL", "http://127.0.0.1:8000/mcp")
    async with Client(endpoint) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        required = {"engineering_skills_list", "engineering_skill_get",
                    "engineering_skill_reference", "engineering_workflow"}
        if not required.issubset(tools):
            raise RuntimeError("MCP engineering skill tools missing")
        catalog = unpack(await client.call_tool("engineering_skills_list", {}))
        assert catalog["revision"] == EXPECTED, "Wrong upstream version"
        assert len(catalog["skills"]) >= 20, "Incomplete upstream catalog"
        tdd = unpack(await client.call_tool("engineering_skill_get", {"name": "tdd"}))
        assert tdd["revision"] == EXPECTED
        assert "Never commit or push" in tdd["priority_policy"]
        assert "Test-Driven Development" in tdd["content"]
        ref = unpack(await client.call_tool("engineering_skill_reference",
                                             {"name": "tdd", "relative_path": "tests.md"}))
        assert ref["content"] and ref["revision"] == EXPECTED
        plan = unpack(await client.call_tool("engineering_workflow", {"task_type": "bugfix"}))
        assert plan["steps"] == ["diagnosing-bugs", "tdd", "code-review"]
        print("CENTRAL_MCP_SKILLS_SMOKE_OK", len(catalog["skills"]), EXPECTED)


if __name__ == "__main__":
    asyncio.run(main())
