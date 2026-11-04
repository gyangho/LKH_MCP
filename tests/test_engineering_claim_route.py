"""Strict Windows Agent claim protocol: old clients cannot skip server skills."""
import asyncio
import json
import unittest
from unittest.mock import patch

import codex_agent_routes
from tests.test_phase_routes import FakeMCP, req


class EngineeringClaimRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        mcp = FakeMCP()
        codex_agent_routes.register_agent_routes(mcp)
        self.endpoint = mcp.routes[("/admin/agent/claim", ("POST",))]

    async def send(self, body):
        payload = json.dumps(body).encode("utf-8")
        return await self.endpoint(req("/admin/agent/claim", "POST", payload))

    async def test_legacy_agent_is_denied_before_queue_claim(self):
        with patch.object(codex_agent_routes, "check_agent_token", return_value=True), \
             patch.object(codex_agent_routes, "claim") as claim:
            response = await self.send({"agent_id": "old-agent", "projects": ["ITAM"]})
        self.assertEqual(response.status_code, 400)
        claim.assert_not_called()

    async def test_supported_agent_can_claim(self):
        with patch.object(codex_agent_routes, "check_agent_token", return_value=True), \
             patch.object(codex_agent_routes, "claim", return_value={"job": None}) as claim:
            response = await self.send({"agent_id": "agent", "projects": ["ITAM"],
                                        "engineering_skills_version": 1})
        self.assertEqual(response.status_code, 200)
        claim.assert_called_once_with("agent", ["ITAM"])

    async def test_bool_is_not_valid_protocol_version(self):
        with patch.object(codex_agent_routes, "check_agent_token", return_value=True), \
             patch.object(codex_agent_routes, "claim") as claim:
            response = await self.send({"agent_id": "agent", "projects": ["ITAM"],
                                        "engineering_skills_version": True})
        self.assertEqual(response.status_code, 400)
        claim.assert_not_called()


if __name__ == "__main__":
    unittest.main()
