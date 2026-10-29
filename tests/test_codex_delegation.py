"""Approval-based Codex delegation tests. No real Codex or Docker is invoked."""
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_delegation as codex


class CodexApprovalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "ITAM"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
        codex._TASKS.clear()
        self.addCleanup(codex._TASKS.clear)
        a = patch.object(codex, "_verified", return_value=(self.root, "owner/ITAM"))
        b = patch.object(codex.settings_store, "get", side_effect=lambda key: {
            "CODEX_DELEGATION_ENABLED": True, "CODEX_MAX_RUNS_PER_DAY": 2}[key])
        a.start(); b.start()
        self.addCleanup(a.stop); self.addCleanup(b.stop)

    def request(self, mode="propose_fix"):
        return codex.request_debug("ITAM", "reproducible authentication failure",
                                   ["src/service.py"], mode=mode)

    def test_request_does_not_start_worker(self):
        with patch.object(codex, "_call_worker", side_effect=AssertionError("must not run")):
            result = self.request()
            self.assertEqual(result["state"], "pending")

    def test_only_debug_modes(self):
        with self.assertRaises(ValueError):
            self.request("implement_feature")

    def test_rejects_sensitive_and_escaping_files(self):
        for name in ("../private.py", ".env", "src/../private.py", "src/token.py"):
            with self.subTest(name=name):
                with self.assertRaises((ValueError, FileNotFoundError)):
                    codex.request_debug("ITAM", "error", [name])

    def test_admin_approval_required(self):
        ident = self.request()["id"]
        with self.assertRaises(PermissionError):
            codex.apply_approved(ident)
        with self.assertRaises(ValueError):
            codex.decide(ident, "approve_apply", "admin@example.test")

    def test_separate_approval_required_for_patch(self):
        ident = self.request()["id"]
        codex.decide(ident, "approve_run", "admin@example.test")
        with codex._LOCK:
            item = codex._TASKS[ident]
            item["state"] = "completed"
            item["patch"] = "-VALUE = 1\n+VALUE = 2\n"
            item["new_files"] = {"src/service.py": b"VALUE = 2\n"}
        with self.assertRaises(PermissionError):
            codex.apply_approved(ident)
        codex.decide(ident, "approve_apply", "admin@example.test")
        response = codex.apply_approved(ident)
        self.assertEqual(response["state"], "applied")
        self.assertFalse(response["pushed"])
        self.assertEqual((self.root / "src" / "service.py").read_text(), "VALUE = 2\n")

    def test_changed_original_is_never_overwritten(self):
        ident = self.request()["id"]
        with codex._LOCK:
            item = codex._TASKS[ident]
            item["state"] = "completed"
            item["new_files"] = {"src/service.py": b"VALUE = 2\n"}
            item["patch"] = "patch"
        codex.decide(ident, "approve_apply", "admin@example.test")
        (self.root / "src" / "service.py").write_text("VALUE = 999\n")
        with self.assertRaises(RuntimeError):
            codex.apply_approved(ident)
        self.assertEqual((self.root / "src" / "service.py").read_text(), "VALUE = 999\n")

    def test_approval_expiration(self):
        ident = self.request()["id"]
        codex.decide(ident, "approve_run", "admin@example.test")
        with codex._LOCK:
            codex._TASKS[ident]["approval_deadline"] = time.monotonic() - 1
        with self.assertRaises(PermissionError):
            codex.run_approved(ident)


if __name__ == "__main__":
    unittest.main()
