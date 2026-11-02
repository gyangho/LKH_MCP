"""Native tray shutdown regression. No actual Windows SCM, UAC or Task is touched."""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import native_tray as tray


class TrayShutdownTests(unittest.TestCase):
    def test_server_shutdown_requests_fixed_scm_only(self):
        binary = Path("C:/Program Files/LKH MCP/LKH-MCP-Service/LKH-MCP-Service.exe")
        with patch.object(tray, "_read_state", return_value={"state": "offline", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=binary), \
             patch.object(tray, "_request_scm_stop") as stop, \
             patch.object(tray, "control_agent") as agent:
            tray.shutdown_from_tray("server")
        stop.assert_called_once_with(binary)
        agent.assert_not_called()

    def test_both_stops_only_registered_agent_before_service(self):
        order = []
        binary = Path("C:/Program Files/LKH MCP/LKH-MCP-Service/LKH-MCP-Service.exe")
        with patch.object(tray, "_read_state", return_value={"state": "online", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=binary), \
             patch.object(tray, "task_state", return_value="running"), \
             patch.object(tray, "control_agent", side_effect=lambda *args, **kw: order.append(("agent", args, kw))), \
             patch.object(tray, "_request_scm_stop", side_effect=lambda *args: order.append(("server", args))):
            tray.shutdown_from_tray("both")
        self.assertEqual(order, [("agent", ("stop",), {"busy": False}),
                                 ("server", (binary,))])

    def test_unknown_busy_or_missing_state_never_stops(self):
        for state in ({"state": "unknown", "busy": False},
                      {"state": "offline", "busy": True},
                      {"state": "online", "busy": None}):
            with self.subTest(state=state), \
                 patch.object(tray, "_read_state", return_value=state), \
                 patch.object(tray, "_request_scm_stop") as stop, \
                 patch.object(tray, "control_agent") as agent:
                with self.assertRaises(PermissionError):
                    tray.shutdown_from_tray("both")
                stop.assert_not_called()
                agent.assert_not_called()

    def test_unavailable_agent_task_denies_combined_stop(self):
        with patch.object(tray, "_read_state", return_value={"state": "online", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=Path("service.exe")), \
             patch.object(tray, "task_state", return_value="unavailable"), \
             patch.object(tray, "_request_scm_stop") as stop:
            with self.assertRaises(RuntimeError):
                tray.shutdown_from_tray("both")
        stop.assert_not_called()

    def test_agent_failure_prevents_server_stop(self):
        with patch.object(tray, "_read_state", return_value={"state": "online", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=Path("service.exe")), \
             patch.object(tray, "task_state", return_value="running"), \
             patch.object(tray, "control_agent", side_effect=RuntimeError("denied")), \
             patch.object(tray, "_request_scm_stop") as stop:
            with self.assertRaises(RuntimeError):
                tray.shutdown_from_tray("both")
        stop.assert_not_called()

    def test_arbitrary_shutdown_target_is_not_supported(self):
        with self.assertRaises(ValueError):
            tray.shutdown_from_tray("other")

    def test_state_missing_busy_is_not_assumed_idle(self):
        payload = MagicMock()
        payload.status = 200
        payload.read.return_value = b'{"state":"online"}'
        payload.__enter__.return_value = payload
        with patch.object(tray.urllib.request, "urlopen", return_value=payload):
            self.assertEqual(tray.status(), "online")
            self.assertIsNone(tray._read_state()["busy"])

    def test_confirmation_defaults_to_no_and_uses_real_line_breaks(self):
        with patch("ctypes.windll", create=True) as win:
            win.user32.MessageBoxW.return_value = 7  # No
            self.assertFalse(tray._confirm_shutdown("server"))
            self.assertIn("\\n", win.user32.MessageBoxW.call_args.args[1])
            self.assertEqual(win.user32.MessageBoxW.call_args.args[3] & 0x100, 0x100)

    def test_frozen_service_path_is_fixed_to_adjacent_package(self):
        with patch.object(tray.sys, "frozen", True, create=True), \
             patch.object(tray.sys, "executable", "C:/LKH/LKH-MCP-Tray/LKH-MCP-Tray.exe"), \
             patch.object(Path, "is_file", return_value=True):
            binary = tray._installed_service_binary()
        self.assertEqual(binary.name, "LKH-MCP-Service.exe")
        self.assertEqual(binary.parent.name, "LKH-MCP-Service")


if __name__ == "__main__":
    unittest.main()
