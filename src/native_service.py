"""Windows SCM host for the native MCP server (I2).

This EXE is the service controller, NOT a tray app. It launches the bundled
headless server in a child process, watches its exit and requests graceful
shutdown through a service-owned one-time stop marker. Installed only with
explicit administrator action (I6).
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path


def server_executable(service_executable: Path) -> Path:
    exe = service_executable.parent.parent / "LKH-MCP-Server" / "LKH-MCP-Server.exe"
    if not exe.is_file():
        raise FileNotFoundError("Bundled LKH-MCP-Server.exe missing")
    return exe


def service_main() -> None:
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    class LkhMcpService(win32serviceutil.ServiceFramework):
        _svc_name_ = "LKH-MCP-Server"
        _svc_display_name_ = "LKH MCP Native Server"
        _svc_description_ = "Native MCP and private administrative gateway"

        def __init__(self, args):
            super().__init__(args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.child = None
            self.stop_marker = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            server = server_executable(Path(sys.executable))
            program_data = os.environ.get("PROGRAMDATA", "")
            if not program_data:
                raise RuntimeError("Missing PROGRAMDATA for SCM service")
            state = Path(os.environ.get("LKH_NATIVE_STATE_DIR") or
                         str(Path(program_data) / "LKH-MCP"))
            if not state.is_absolute():
                raise RuntimeError("State path must be absolute")
            logs = state / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            marker = logs / ("stop-" + secrets.token_hex(16) + ".signal")
            self.stop_marker = marker
            with (logs / "service-supervisor.log").open("a", encoding="utf-8") as output:
                self.child = subprocess.Popen(
                    [str(server), "--stop-file", str(marker)],
                    cwd=str(server.parent),
                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    close_fds=True,
                )
                try:
                    while True:
                        if self.child.poll() is not None:
                            raise RuntimeError("LKH MCP native server exited unexpectedly")
                        if win32event.WaitForSingleObject(self.stop_event, 500) == win32event.WAIT_OBJECT_0:
                            marker.touch(exist_ok=False)
                            try:
                                self.child.wait(timeout=25)
                            except subprocess.TimeoutExpired:
                                self.child.terminate()
                                self.child.wait(timeout=10)
                            break
                finally:
                    if self.child and self.child.poll() is None:
                        self.child.terminate()
                        self.child.wait(timeout=10)
                    marker.unlink(missing_ok=True)

    if len(sys.argv) > 1:
        win32serviceutil.HandleCommandLine(LkhMcpService)
    else:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(LkhMcpService)
        servicemanager.StartServiceCtrlDispatcher()


if __name__ == "__main__":
    if os.name != "nt":
        raise RuntimeError("Windows Service only supported on Windows")
    service_main()
