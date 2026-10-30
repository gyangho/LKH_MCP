"""Native task control and tray status unit checks (without real Windows tasks)."""
import unittest
from unittest.mock import patch, MagicMock
import json
import io

import native_task_control as task
import native_tray as tray
from native_host_routes import compute_tray_state


class TaskTests(unittest.TestCase):
    def test_fixed_task_name_and_no_shell(self):
        with patch.object(task, "_windows_only"), patch.object(
            task.subprocess, "run", return_value=MagicMock(returncode=0)
        ) as run:
            result = task.control_agent("start")
        self.assertTrue(result["accepted"])
        args, kw = run.call_args
        self.assertEqual(args[0], ["schtasks.exe", "/run", "/tn", r"\LKH-Codex-Agent"])
        self.assertIs(kw["shell"], False)

    def test_busy_tasks_cannot_be_stopped(self):
        with patch.object(task, "_windows_only"):
            for action in ("stop", "restart"):
                with self.assertRaises(PermissionError):
                    task.control_agent(action, busy=True)

    def test_unknown_action_rejected(self):
        with patch.object(task, "_windows_only"), self.assertRaises(ValueError):
            task.control_agent("powershell -Command Write-Host danger")

    def test_failure_fails_closed(self):
        with patch.object(task, "_windows_only"), patch.object(
            task.subprocess, "run", return_value=MagicMock(returncode=1)
        ), self.assertRaises(RuntimeError):
            task.control_agent("start")

    def test_pig_requires_recent_authenticated_heartbeat(self):
        online_agent = {"online": True, "busy": False}
        active = {"enabled": True, "token_configured": True,
                  "agents": [online_agent]}
        self.assertEqual(compute_tray_state(active, "running")["state"], "online")
        for changed in (
            {"agents": [{"online": False}]},
            {"enabled": False},
            {"token_configured": False},
            {"agents": []},
        ):
            state = dict(active, **changed)
            self.assertEqual(compute_tray_state(state, "running")["state"], "offline")
        for task_state_value in ("ready", "disabled", "queued"):
            self.assertEqual(compute_tray_state(active, task_state_value)["state"], "offline")
        self.assertEqual(compute_tray_state(active, "unavailable")["state"], "unknown")

    def test_tray_requires_server_verdict_not_scheduler_state(self):
        def reply(status, payload):
            value = MagicMock()
            value.status = status
            value.read.return_value = json.dumps(payload).encode("utf-8")
            value.__enter__.return_value = value
            return value
        for verdict in ("online", "offline", "unknown"):
            with self.subTest(verdict=verdict), patch.object(
                tray.urllib.request, "urlopen",
                return_value=reply(200, {"state": verdict})
            ) as fetch:
                self.assertEqual(tray.status(), verdict)
                self.assertTrue(fetch.call_args.args[0].endswith("/admin/host/tray-state"))
        with patch.object(tray.urllib.request, "urlopen",
                          return_value=reply(200, {"state": "invalid"})):
            self.assertEqual(tray.status(), "unknown")
        with patch.object(tray.urllib.request, "urlopen", side_effect=OSError):
            self.assertEqual(tray.status(), "unknown")



if __name__ == "__main__":
    unittest.main()
