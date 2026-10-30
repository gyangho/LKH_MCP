"""Phase 9 contract smoke tests. Never touches production data/Windows services."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SkillContractTests(unittest.TestCase):
    def test_skill_name_and_safety_policy(self):
        skill = (ROOT / ".agents" / "skills" / "lkh-development" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\nname: lkh-development\n"))
        for term in ("refac", "mcp", "admin", "SQLite", "Phase", "no", "approval"):
            self.assertIn(term.lower(), skill.lower())

    def test_phase_artifacts_syntax(self):
        targets = (
            "src/codex_events.py", "src/instruction_store.py", "src/instruction_routes.py",
            "src/operations_store.py", "src/operations_routes.py", "src/server.py",
            "windows_agent/agent.py",
        )
        for path in targets:
            with self.subTest(path=path):
                ast.parse((ROOT / path).read_text(encoding="utf-8"))

    def test_release_gates_documented(self):
        roadmap = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
        ledger = (ROOT / "docs" / "PHASES_1_9_STATUS.md").read_text(encoding="utf-8")
        for phase in range(1, 10):
            self.assertIn(f"| **{phase}** ", roadmap)
            self.assertIn(f"| {phase} |", ledger)
        self.assertIn("cutover", ledger.lower())
        self.assertIn("not production", ledger.lower())


if __name__ == "__main__":
    unittest.main()
