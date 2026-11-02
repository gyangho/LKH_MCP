"""Service CLI contract; never registers or starts a real Windows service."""
import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == "nt", "requires pywin32")
class NativeServiceTests(unittest.TestCase):
    def test_service_class_is_resolvable_by_pywin32(self):
        import native_service as service
        import win32serviceutil
        name = win32serviceutil.GetServiceClassString(service.LkhMcpService)
        self.assertEqual(name, "native_service.LkhMcpService")

    def test_cli_failure_is_returned_to_entrypoint(self):
        import native_service as service
        with patch.object(service.sys, "argv", ["service.exe", "install"]), \
             patch.object(service.win32serviceutil, "HandleCommandLine", return_value=5):
            self.assertEqual(service.service_main(), 5)

    def test_scm_dispatch_still_hosts_same_class(self):
        import native_service as service
        with patch.object(service.sys, "argv", ["service.exe"]), \
             patch.object(service.servicemanager, "Initialize"), \
             patch.object(service.servicemanager, "PrepareToHostSingle") as host, \
             patch.object(service.servicemanager, "StartServiceCtrlDispatcher"):
            self.assertEqual(service.service_main(), 0)
        host.assert_called_once_with(service.LkhMcpService)

    def test_real_pywin32_install_dispatch_and_error_code(self):
        import native_service as service
        # Exercise the real command parser and class resolver, replacing only SCM I/O.
        args = ["service.exe", "--startup", "auto", "--username",
                "NT AUTHORITY\\LocalService", "install"]
        with patch.object(service.sys, "argv", args), \
             patch.object(service.win32serviceutil, "InstallService") as install:
            self.assertEqual(service.service_main(), 0)
        self.assertEqual(install.call_args.args[0], "native_service.LkhMcpService")
        self.assertEqual(install.call_args.args[1], "LKH-MCP-Server")
        self.assertEqual(install.call_args.kwargs["userName"], "NT AUTHORITY\\LocalService")
        with patch.object(service.sys, "argv", args), \
             patch.object(service.win32serviceutil, "InstallService",
                          side_effect=service.win32service.error(5, "CreateService", "denied")):
            self.assertEqual(service.service_main(), 5)
