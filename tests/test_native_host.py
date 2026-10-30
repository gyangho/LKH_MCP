"""Native task control and tray status unit checks (without real Windows tasks)."""
import unittest
from unittest.mock import patch, MagicMock

import native_task_control as task
import native_tray as tray


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

    def test_pig_state_meanings(self):
        with patch.object(tray, "server_healthy", return_value=False):
            self.assertEqual(tray.status(), "unknown")
        with patch.object(tray, "server_healthy", return_value=True):
            for state, expected in (("running", "online"), ("ready", "offline"),
                                    ("disabled", "offline"), ("unavailable", "unknown")):
                with patch.object(tray, "task_state", return_value=state):
                    self.assertEqual(tray.status(), expected)


if __name__ == "__main__":
    unittest.main()
