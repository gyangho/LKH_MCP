"""Native tray shutdown regression. No actual Windows SCM, UAC or Task is touched."""
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import native_tray as tray


class TrayShutdownTests(unittest.TestCase):
    def test_progress_reports_agent_uac_and_service_wait_in_order(self):
        progress = []
        with patch.object(tray, "_read_state", return_value={"state": "online", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=Path("service.exe")), \
             patch.object(tray, "task_state", return_value="running"), \
             patch.object(tray, "control_agent"), patch.object(tray, "_wait_for_agent_stop"), \
             patch.object(tray, "_request_scm_stop"), patch.object(tray, "_wait_for_service_stop"):
            tray.shutdown_from_tray("both", progress=progress.append)
        self.assertIn("Codex", progress[0])
        self.assertIn("Agent 중지", progress[2])
        self.assertIn("UAC", progress[3])
        self.assertIn("서비스 중지", progress[4])

    def test_server_shutdown_requests_fixed_scm_only(self):
        binary = Path("C:/Program Files/LKH MCP/LKH-MCP-Service/LKH-MCP-Service.exe")
        with patch.object(tray, "_read_state", return_value={"state": "offline", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=binary), \
             patch.object(tray, "_request_scm_stop") as stop, \
             patch.object(tray, "_wait_for_service_stop") as waited, \
             patch.object(tray, "control_agent") as agent:
            tray.shutdown_from_tray("server")
        stop.assert_called_once_with(binary)
        waited.assert_called_once_with()
        agent.assert_not_called()

    def test_both_stops_only_registered_agent_before_service(self):
        order = []
        binary = Path("C:/Program Files/LKH MCP/LKH-MCP-Service/LKH-MCP-Service.exe")
        with patch.object(tray, "_read_state", return_value={"state": "online", "busy": False}), \
             patch.object(tray, "_installed_service_binary", return_value=binary), \
             patch.object(tray, "task_state", return_value="running"), \
             patch.object(tray, "control_agent", side_effect=lambda *args, **kw: order.append(("agent", args, kw))), \
             patch.object(tray, "_wait_for_agent_stop", side_effect=lambda: order.append(("agent_confirmed",))), \
             patch.object(tray, "_request_scm_stop", side_effect=lambda *args: order.append(("server", args))), \
             patch.object(tray, "_wait_for_service_stop", side_effect=lambda: order.append(("server_confirmed",))):
            tray.shutdown_from_tray("both")
        self.assertEqual(order, [("agent", ("stop",), {"busy": False}),
                                 ("agent_confirmed",), ("server", (binary,)),
                                 ("server_confirmed",)])

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

    def test_tray_exposes_only_combined_shutdown_menu(self):
        source = (Path(__file__).resolve().parents[1] / "src/native_tray.py").read_text(encoding="utf-8")
        self.assertIn('Item("종료", lambda i, t: do_shutdown("both"))', source)
        self.assertNotIn('Item("트레이', source)
        self.assertNotIn('Item("MCP 서버 종료', source)
        self.assertNotIn('Item("서버 + Agent 모두 종료', source)

    def test_agent_stop_waits_for_ready_and_refuses_unknown(self):
        with patch.object(tray, "task_state", side_effect=["running", "ready"]), \
             patch.object(tray.time, "sleep") as sleeper:
            tray._wait_for_agent_stop()
        sleeper.assert_called_once()
        with patch.object(tray, "task_state", return_value="unavailable"):
            with self.assertRaises(RuntimeError):
                tray._wait_for_agent_stop()

    def test_service_stop_requires_scm_stopped_and_closes_handles(self):
        manager, service, closed = object(), object(), []
        scm = SimpleNamespace(
            SC_MANAGER_CONNECT=1, SERVICE_QUERY_STATUS=4, SERVICE_STOPPED=1,
            OpenSCManager=lambda *args: manager,
            OpenService=lambda *args: service,
            QueryServiceStatus=MagicMock(side_effect=[(0, 3), (0, 1)]),
            CloseServiceHandle=lambda handle: closed.append(handle),
        )
        with patch.dict(sys.modules, {"win32service": scm}), \
             patch.object(tray.time, "sleep") as sleeper:
            tray._wait_for_service_stop()
        self.assertEqual(scm.QueryServiceStatus.call_count, 2)
        self.assertEqual(closed, [service, manager])
        sleeper.assert_called_once()

    def test_service_wait_timeout_still_closes_handles(self):
        manager, service, closed = object(), object(), []
        scm = SimpleNamespace(
            SC_MANAGER_CONNECT=1, SERVICE_QUERY_STATUS=4, SERVICE_STOPPED=1,
            OpenSCManager=lambda *args: manager,
            OpenService=lambda *args: service,
            QueryServiceStatus=lambda *args: (0, 3),
            CloseServiceHandle=lambda handle: closed.append(handle),
        )
        with patch.dict(sys.modules, {"win32service": scm}), \
             patch.object(tray.time, "monotonic", side_effect=[0, 31]):
            with self.assertRaises(TimeoutError):
                tray._wait_for_service_stop(timeout=30)
        self.assertEqual(closed, [service, manager])

    def test_error_dialog_is_topmost_for_hidden_notification_failure(self):
        with patch("ctypes.windll", create=True) as win:
            tray._show_shutdown_result("Agent 작업 상태 확인 실패", failed=True)
        messagebox = win.user32.MessageBoxW.call_args.args
        self.assertIn("Agent 작업 상태 확인 실패", messagebox[1])
        self.assertTrue(messagebox[3] & 0x40000)

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
            self.assertIn("\n", win.user32.MessageBoxW.call_args.args[1])
            self.assertIn("상태를 확인할 수 없으면", win.user32.MessageBoxW.call_args.args[1])
            self.assertNotIn("작업이 실행 중이면 중단", win.user32.MessageBoxW.call_args.args[1])
            self.assertEqual(win.user32.MessageBoxW.call_args.args[3] & 0x100, 0x100)

    def test_connection_refused_shows_persistent_reason_without_stop(self):
        with patch.object(tray.urllib.request, "urlopen", side_effect=OSError("refused")), \
             patch.object(tray, "_request_scm_stop") as stop, \
             patch.object(tray, "control_agent") as agent, \
             patch("ctypes.windll", create=True) as win:
            tray._shutdown_with_feedback("both")
        stop.assert_not_called()
        agent.assert_not_called()
        dialog = win.user32.MessageBoxW.call_args
        self.assertIn("로컬 서버", dialog.args[1])
        self.assertIn("설치·실행 상태", dialog.args[1])
        self.assertNotIn("UAC", dialog.args[1])
        self.assertEqual(dialog.args[2], "LKH MCP 종료 실패")

    def test_busy_and_unknown_busy_have_distinct_feedback(self):
        for busy, reason in ((True, "실행 중"), (None, "작업 상태를 확인할 수 없어")):
            with self.subTest(busy=busy), \
                 patch.object(tray, "_read_state", return_value={"state": "online", "busy": busy}), \
                 patch.object(tray, "_show_shutdown_result") as show, \
                 patch.object(tray, "_request_scm_stop") as stop:
                tray._shutdown_with_feedback("both")
                self.assertIn(reason, show.call_args.args[0])
                self.assertTrue(show.call_args.kwargs["failed"])
                stop.assert_not_called()

    def test_unexpected_failure_is_visible_and_redacted(self):
        with patch.object(tray, "shutdown_from_tray", side_effect=Exception("sensitive details")), \
             patch.object(tray, "_show_shutdown_result") as show:
            tray._shutdown_with_feedback("both")
        self.assertTrue(show.call_args.kwargs["failed"])
        self.assertNotIn("sensitive details", show.call_args.args[0])

    def test_verified_shutdown_allows_tray_to_close(self):
        with patch.object(tray, "shutdown_from_tray"), \
             patch.object(tray, "_show_shutdown_result") as show:
            self.assertTrue(tray._shutdown_with_feedback("both"))
        show.assert_not_called()

    def test_frozen_service_path_is_fixed_to_adjacent_package(self):
        with patch.object(tray.sys, "frozen", True, create=True), \
             patch.object(tray.sys, "executable", "C:/LKH/LKH-MCP-Tray/LKH-MCP-Tray.exe"), \
             patch.object(Path, "is_file", return_value=True):
            binary = tray._installed_service_binary()
        self.assertEqual(binary.name, "LKH-MCP-Service.exe")
        self.assertEqual(binary.parent.name, "LKH-MCP-Service")


if __name__ == "__main__":
    unittest.main()
