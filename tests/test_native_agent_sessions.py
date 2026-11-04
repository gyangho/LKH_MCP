"""Start the fixed Agent in its registered user's session, never the caller's."""
import sys
import unittest
from types import ModuleType
from unittest.mock import MagicMock, patch

import native_task_control as control


class AgentSessionTests(unittest.TestCase):
    def setUp(self):
        self.sid = "S-1-5-21-1001"
        package, self.client, self.com, self.ts, self.security = (
            ModuleType(name) for name in ("win32com", "win32com.client", "pythoncom",
                                          "win32ts", "win32security"))
        package.client = self.client
        self.com.CoInitialize = MagicMock()
        self.com.CoUninitialize = MagicMock()
        self.scheduler = MagicMock()
        self.task = self.scheduler.GetFolder.return_value.GetTask.return_value
        self.task.State = 3
        self.task.Definition.Principal.UserId = self.sid
        self.task.Definition.Principal.LogonType = 3
        self.client.Dispatch = MagicMock(return_value=self.scheduler)
        self.ts.WTS_CURRENT_SERVER_HANDLE = 0
        self.ts.WTSActive = 0
        self.ts.WTSUserName = 5
        self.ts.WTSDomainName = 7
        self.ts.WTSEnumerateSessions = MagicMock(return_value=[{"SessionId": 3, "State": 0}])
        self.ts.WTSQuerySessionInformation = MagicMock(side_effect=
            lambda server, session, field: "User" if field == 5 else "HOST")
        self.security.ConvertStringSidToSid = MagicMock(side_effect=lambda sid: sid)
        self.security.ConvertSidToStringSid = MagicMock(side_effect=lambda sid: sid)
        self.security.LookupAccountName = MagicMock(return_value=(self.sid, "HOST", 1))
        self.patches = [patch.object(control, "_windows_only"), patch.dict(sys.modules, {
            "win32com": package, "win32com.client": self.client, "pythoncom": self.com,
            "win32ts": self.ts, "win32security": self.security}),
            patch.object(control.subprocess, "run", side_effect=AssertionError("Implicit schtasks start is unsafe"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_start_explicitly_targets_registered_user_and_session(self):
        result = control.control_agent("start")
        self.assertTrue(result["accepted"])
        self.scheduler.GetFolder.assert_called_once_with("\\")
        self.scheduler.GetFolder.return_value.GetTask.assert_called_once_with("LKH-Codex-Agent")
        # USE_SESSION_ID | USER_SID; not AS_SELF or IGNORE_CONSTRAINTS.
        self.task.RunEx.assert_called_once_with(None, 12, 3, self.sid)
        self.com.CoUninitialize.assert_called_once_with()

    def test_other_users_session_cannot_be_selected(self):
        self.security.LookupAccountName.return_value = ("S-1-5-21-9999", "HOST", 1)
        with self.assertRaises(RuntimeError):
            control.control_agent("start")
        self.task.RunEx.assert_not_called()
        self.com.CoUninitialize.assert_called_once_with()

    def test_disconnected_session_is_not_selected(self):
        self.ts.WTSEnumerateSessions.return_value = [{"SessionId": 3, "State": 4}]
        with self.assertRaises(RuntimeError):
            control.control_agent("start")
        self.task.RunEx.assert_not_called()

    def test_ambiguous_sessions_fail_closed(self):
        self.ts.WTSEnumerateSessions.return_value = [
            {"SessionId": 3, "State": 0}, {"SessionId": 7, "State": 0}]
        with self.assertRaises(RuntimeError):
            control.control_agent("start")
        self.task.RunEx.assert_not_called()

    def test_restart_resolves_session_before_stopping_existing_agent(self):
        self.task.State = 4
        self.ts.WTSEnumerateSessions.return_value = []
        with self.assertRaises(RuntimeError):
            control.control_agent("restart")
        self.task.Stop.assert_not_called()
        self.task.RunEx.assert_not_called()

    def test_restart_stops_then_runs_in_same_registered_session(self):
        self.task.State = 4
        self.task.Stop.side_effect = lambda flags: setattr(self.task, "State", 3)
        control.control_agent("restart")
        self.task.Stop.assert_called_once_with(0)
        self.task.RunEx.assert_called_once_with(None, 12, 3, self.sid)

    def test_start_running_task_is_idempotent(self):
        self.task.State = 4
        self.assertTrue(control.control_agent("start")["accepted"])
        self.task.RunEx.assert_not_called()
        self.task.Stop.assert_not_called()

    def test_session_query_failure_is_sanitized(self):
        self.ts.WTSQuerySessionInformation.side_effect = RuntimeError("private-user-detail")
        with self.assertRaises(RuntimeError) as caught:
            control.control_agent("start")
        self.assertNotIn("private-user-detail", str(caught.exception))
        self.task.RunEx.assert_not_called()
        self.com.CoUninitialize.assert_called_once_with()

    def test_disabled_task_is_not_enabled_implicitly(self):
        self.task.State = 1
        with self.assertRaises(RuntimeError):
            control.control_agent("start")
        self.task.RunEx.assert_not_called()

    def test_noninteractive_principal_is_rejected(self):
        self.task.Definition.Principal.LogonType = 5
        with self.assertRaises(RuntimeError):
            control.control_agent("start")
        self.task.RunEx.assert_not_called()


if __name__ == "__main__":
    unittest.main()
