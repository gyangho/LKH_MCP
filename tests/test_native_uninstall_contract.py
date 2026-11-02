"""Uninstaller safety contract (source checks run on every Python CI build)."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class UninstallerContractTests(unittest.TestCase):
    def test_three_modes_and_default_sqlite_preservation(self):
        source = (ROOT / "installer/LKH-MCP.iss").read_text("utf-8")
        self.assertIn("RemovalMode := 'settings'", source)
        self.assertIn("SelectUninstallMode()", source)
        self.assertIn("FullRemoval.Checked := False", source)
        self.assertIn("if FullRemoval.Checked then", source)
        self.assertIn("Form.ShowModal", source)
        self.assertNotIn("RemovalMode := 'program'", source)
        self.assertNotIn("MB_YESNOCANCEL", source)
        self.assertIn("MB_OKCANCEL or MB_DEFBUTTON2", source)
        # Existing program mode stays in fixed cleanup script, not the UI selector.
        self.assertIn("RemovalMode := 'all'", source)
        self.assertIn("RunNativeRemoval('verify')", source)
        self.assertIn("RunNativeRemoval('remove')", source)
        self.assertNotIn("[UninstallRun]", source.split("[Code]")[0])

    def test_exact_owned_task_service_and_no_ambient_deletes(self):
        ps = (ROOT / "scripts/native-uninstall.ps1").read_text("utf-8")
        for fixed in ("LKH-Codex-Agent", "LKH-MCP-Tray", "LKH-MCP-Server",
                      "NoReparse", "OwnedTask", "OwnedService", "busy",
                      "LKH-MCP-RemovalBackups", "mcp.sqlite3"):
            self.assertIn(fixed, ps)
        self.assertIn("if ($Mode -eq 'settings'", ps)
        self.assertIn("if ($Mode -eq 'all'", ps)
        self.assertNotIn("docker compose down", ps)

    def test_reenrollment_is_gated_by_settings_reset_marker(self):
        ps = (ROOT / "scripts/native-uninstall.ps1").read_text("utf-8")
        py = (ROOT / "src/native_enrollment.py").read_text("utf-8")
        marker = ".enrollment-reset-by-uninstall"
        self.assertIn(marker, ps)
        self.assertIn(marker, py)

if __name__ == "__main__":
    unittest.main()
