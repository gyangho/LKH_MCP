"""Separate Windows tray UI; never hosts MCP or exposes credentials.

Pixel Pig is generated from the approved branding image. The local tray
reads the server's loopback authenticated-heartbeat status and invokes one fixed task.
The server continues if this user-session process exits.
"""
from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from native_task_control import control_agent, task_state


_LOG = logging.getLogger("lkh.tray")


def _configure_logging():
    """The interactive user can read/write this log; no server secrets or OS error text."""
    if _LOG.handlers:
        return
    _LOG.addHandler(logging.NullHandler())
    _LOG.propagate = False
    try:
        local = os.environ.get("LOCALAPPDATA", "")
        if not local:
            return
        directory = Path(local) / "LKH-MCP" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "tray.log", maxBytes=512000,
                                      backupCount=1, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _LOG.addHandler(handler)
        _LOG.setLevel(logging.INFO)
    except OSError:
        pass


def assets_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"


def _admin_base() -> str:
    from native_network import admin_base
    return admin_base()


def _read_state() -> dict:
    """Only the loopback Native server can report authenticated Agent/busy state.

    Missing busy metadata must NOT be interpreted as idle for stop actions.
    """
    unknown = {"state": "unknown", "busy": None}
    try:
        with urllib.request.urlopen(_admin_base() + "/admin/host/tray-state",
                                    timeout=2) as result:
            if result.status != 200:
                return unknown
            payload = json.loads(result.read(512).decode("utf-8"))
        if not isinstance(payload, dict):
            return unknown
        state, busy = payload.get("state"), payload.get("busy")
        if state not in ("online", "offline", "unknown"):
            return unknown
        return {"state": state, "busy": busy if type(busy) is bool else None}
    except (OSError, ValueError, TypeError, UnicodeError):
        return unknown


def status() -> str:
    return _read_state()["state"]


def _service_state() -> str:
    """Read SCM independently of HTTP/Agent health; failure is never STOPPED."""
    try:
        import win32service
        manager = win32service.OpenSCManager(
            None, None, win32service.SC_MANAGER_CONNECT)
        try:
            service = win32service.OpenService(
                manager, "LKH-MCP-Server", win32service.SERVICE_QUERY_STATUS)
            try:
                state = win32service.QueryServiceStatus(service)[1]
                if state == win32service.SERVICE_STOPPED:
                    return "stopped"
                if state == win32service.SERVICE_RUNNING:
                    return "running"
                return "pending"
            finally:
                win32service.CloseServiceHandle(service)
        finally:
            win32service.CloseServiceHandle(manager)
    except Exception as exc:
        code = getattr(exc, "winerror", None)
        if code is None and exc.args and isinstance(exc.args[0], int):
            code = exc.args[0]
        if code == 1060:
            _LOG.info("SCM service missing")
            return "missing"
        _LOG.warning("SCM query failed: type=%s code=%s", type(exc).__name__, code)
        return "unknown"


def _installed_service_binary() -> Path:
    """Resolve only the adjacent, installer-owned SCM controller executable."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Native Installer tray is required to stop the service")
    service = (Path(sys.executable).resolve().parent.parent /
               "LKH-MCP-Service" / "LKH-MCP-Service.exe")
    if not service.is_file():
        raise RuntimeError("LKH-MCP-Service.exe is not installed")
    return service


def _request_scm_action(executable: Path, action: str) -> None:
    """Request an OS-authorized stop through UAC, never an unauthenticated HTTP API."""
    import ctypes
    from ctypes import wintypes
    if os.name != "nt":
        raise RuntimeError("Windows SCM is required")
    if action not in ("start", "stop"):
        raise ValueError("Unsupported fixed service action")
    command = "--wait 30 start" if action == "start" else "stop"
    # The executable and command are fixed: no caller-supplied shell or service name.
    launch = ctypes.windll.shell32.ShellExecuteW
    launch.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                       wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    launch.restype = wintypes.HINSTANCE
    result = launch(None, "runas", str(executable), command, str(executable.parent), 0)
    if int(result or 0) <= 32:
        raise PermissionError("Windows UAC denied or could not launch the service action")
    # ShellExecuteW acknowledges launch only, not completed service shutdown.


def _request_scm_stop(executable: Path) -> None:
    _request_scm_action(executable, "stop")


def _start_server_with_feedback() -> bool:
    from native_installation import allowed
    from native_tray_progress import show_shutdown_progress

    def operation(report):
        try:
            report("설치 완료 상태 확인 중…")
            if not allowed():
                return "설치가 완료되지 않았거나 실패했습니다. 설치 프로그램을 정상 완료한 뒤 다시 실행하세요."
            current = _service_state()
            if current == "missing":
                return "서버 서비스가 설치되어 있지 않습니다. 설치 프로그램으로 복구하세요."
            if current == "unknown":
                return "Windows 서비스 상태를 확인할 수 없습니다. 트레이 로그와 서비스 조회 권한을 확인하세요."
            if current == "stopped":
                report("Windows 관리자 승인 대기 중… UAC 창을 확인하세요.")
                _request_scm_action(_installed_service_binary(), "start")
            report("서버 서비스 시작 확인 중…")
            deadline = time.monotonic() + 45
            while _service_state() != "running":
                if time.monotonic() >= deadline:
                    return "서버 서비스가 제한 시간 내 시작되지 않았습니다. 서비스 로그를 확인하세요."
                time.sleep(0.4)
            report("관리자 리스너 준비 확인 중…")
            deadline = time.monotonic() + 20
            from version import VERSION
            while True:
                try:
                    with urllib.request.urlopen(_admin_base() + "/admin/healthz", timeout=2) as response:
                        data = json.loads(response.read(1024))
                        if (response.status == 200 and data.get("application") == "LKH-MCP"
                                and data.get("version") == VERSION and data.get("status") == "ok"):
                            _LOG.info("server startup confirmed version=%s", VERSION)
                            return None
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
                if time.monotonic() >= deadline:
                    return "서버 프로세스는 시작됐지만 관리자 리스너 준비를 확인하지 못했습니다. 서버 로그를 확인하세요."
                time.sleep(0.4)
        except Exception as exc:
            _LOG.error("server startup failed: %s", type(exc).__name__)
            return "서버 시작 요청에 실패했습니다. UAC 승인 여부와 트레이 로그를 확인하세요."

    try:
        error = show_shutdown_progress(operation, title="LKH MCP 시작 중",
            initial_message="서버 시작 준비 중…",
            stages=(("설치", 10), ("Windows", 30), ("서버 서비스", 60), ("관리자 리스너", 85)))
    except Exception as exc:
        _LOG.error("startup progress failed: %s", type(exc).__name__)
        error = ("시작 진행창이 중단됐습니다. 서비스 상태와 트레이 로그를 확인하세요."
                 if getattr(exc, "operation_started", False) else operation(lambda text: None))
    if error is not None:
        _show_shutdown_result(error, failed=True, action="서버 시작")
        return False
    return True


class ShutdownBlocked(PermissionError):
    """Safe, user-facing reason why shutdown could not proceed."""


class ShutdownFailure(RuntimeError):
    """Safe, user-facing failure after shutdown checks."""

def _wait_for_agent_stop(*, timeout: float = 15.0) -> None:
    """The scheduler accepting /end does not prove the Agent stopped."""
    deadline = time.monotonic() + timeout
    while True:
        state = task_state()
        if state in ("ready", "disabled"):
            return
        if state not in ("running", "queued"):
            raise RuntimeError("Agent 작업 상태를 확인할 수 없어 종료를 중단했습니다.")
        if time.monotonic() >= deadline:
            raise TimeoutError("Agent 작업이 제한 시간 내 중지되지 않았습니다.")
        time.sleep(0.3)


def _wait_for_service_stop(*, timeout: float = 30.0) -> None:
    """Only a verified STOPPED SCM state counts as successful shutdown."""
    import win32service

    manager = win32service.OpenSCManager(
        None, None, win32service.SC_MANAGER_CONNECT)
    try:
        service = win32service.OpenService(
            manager, "LKH-MCP-Server", win32service.SERVICE_QUERY_STATUS)
        try:
            deadline = time.monotonic() + timeout
            while True:
                current = win32service.QueryServiceStatus(service)[1]
                if current == win32service.SERVICE_STOPPED:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError("MCP 서비스가 제한 시간 내 중지되지 않았습니다.")
                time.sleep(0.4)
        finally:
            win32service.CloseServiceHandle(service)
    finally:
        win32service.CloseServiceHandle(manager)




def shutdown_from_tray(target: str, *, progress=None) -> None:
    """Safely request shutdown using Windows SCM privileges and Task Scheduler ACLs.

    The tray has no administrator browser cookie; it must never bypass session/CSRF.
    """
    if target not in ("server", "both"):
        raise ValueError("Unknown fixed shutdown target")
    report = progress or (lambda message: None)
    report("서버 연결과 실행 중인 Codex 작업 확인 중…")
    verdict = _read_state()
    if verdict["state"] not in ("online", "offline"):
        raise ShutdownBlocked("로컬 서버에 연결하거나 상태를 확인할 수 없어 종료 요청을 보내지 않았습니다.\n"
                              "Windows 서비스에서 LKH MCP Native Server의 설치·실행 상태를 확인하세요.")
    if verdict["busy"] is True:
        raise ShutdownBlocked("Codex 작업이 실행 중이어서 종료 요청을 보내지 않았습니다.\n"
                              "관리자 페이지에서 작업을 완료하거나 취소한 뒤 다시 시도하세요.")
    if verdict["busy"] is not False:
        raise ShutdownBlocked("Codex 작업 상태를 확인할 수 없어 종료 요청을 보내지 않았습니다.\n"
                              "관리자 페이지에서 작업 상태를 확인한 뒤 다시 시도하세요.")
    try:
        service_binary = _installed_service_binary()
    except (OSError, RuntimeError) as exc:
        raise ShutdownFailure("서비스 제어 프로그램을 찾을 수 없어 종료하지 못했습니다.\n"
                              "LKH MCP 설치 상태를 확인하세요.") from exc
    if target == "both":
        try:
            report("Agent 작업 스케줄러 상태 확인 중…")
            scheduler = task_state()
        except Exception as exc:
            raise ShutdownFailure("Agent 작업 스케줄러 상태를 확인하지 못해 서버 종료를 요청하지 않았습니다.\n"
                                  "작업 스케줄러의 LKH-Codex-Agent 등록 상태와 권한을 확인하세요.") from exc
        if scheduler not in ("running", "ready", "disabled"):
            raise ShutdownFailure("Agent가 대기 중인지 확인할 수 없어 서버 종료를 요청하지 않았습니다.\n"
                                  "작업 스케줄러의 LKH-Codex-Agent 상태를 확인한 뒤 다시 시도하세요.")
        if scheduler == "running":
            try:
                report("Agent 중지 요청 및 중지 상태 확인 중…")
                control_agent("stop", busy=False)
                _wait_for_agent_stop()
            except Exception as exc:
                raise ShutdownFailure("Agent 중지에 실패해 서버 종료를 요청하지 않았습니다.\n"
                                      "작업 스케줄러의 LKH-Codex-Agent 상태와 권한을 확인하세요.") from exc
    try:
        report("Windows 관리자 승인 대기 중… UAC 창을 확인하세요.")
        _request_scm_stop(service_binary)
    except (OSError, RuntimeError) as exc:
        raise ShutdownFailure("Windows 서비스 종료 프로그램을 실행하지 못했습니다.\n"
                              "UAC 승인이 취소되었거나 실행 권한이 없을 수 있습니다. 다시 시도하세요.") from exc
    try:
        report("MCP 서버 서비스 중지 확인 중… (최대 30초)")
        _wait_for_service_stop()
    except Exception as exc:
        raise ShutdownFailure("서비스 중지를 확인하지 못했습니다. Windows 서비스 상태와 권한을 확인하세요.") from exc


def _confirm_shutdown(target: str) -> bool:
    import ctypes
    name = "MCP 서버와 Agent" if target == "both" else "MCP 서버"
    message = (name + "를 종료하시겠습니까?\n"
               "작업이 실행 중이거나 상태를 확인할 수 없으면 종료 요청을 보내지 않습니다.\n"
               "서비스 종료 요청 시 Windows 관리자(UAC) 승인이 필요합니다.\n"
               "취소하면 종료하지 않습니다.")
    # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 (No)
    return ctypes.windll.user32.MessageBoxW(None, message, "LKH MCP 종료 확인",
                                            0x4 | 0x30 | 0x100 | 0x10000 | 0x40000) == 6


def _show_shutdown_result(message: str, *, failed: bool, action: str = "종료") -> None:
    import ctypes
    # A modal result stays visible even when Windows tray notifications are disabled.
    ctypes.windll.user32.MessageBoxW(
        None, message, "LKH MCP " + action + (" 실패" if failed else " 요청"),
        (0x10 if failed else 0x40) | 0x10000 | 0x40000)


def _shutdown_with_feedback(target: str, *, progress=None) -> bool:
    try:
        if progress is None:
            shutdown_from_tray(target)
        else:
            shutdown_from_tray(target, progress=progress)
    except (ShutdownBlocked, ShutdownFailure) as exc:
        _show_shutdown_result(str(exc), failed=True)
    except Exception:
        # Never expose raw OS/COM errors or paths in the UI.
        _show_shutdown_result("종료 처리 중 오류가 발생했습니다. Windows 서비스와 Agent 상태를 확인하세요.",
                              failed=True)
    else:
        return True  # SCM STOPPED was observed; the caller may close the tray.
    return False



def _shutdown_progress_window(target: str) -> bool:
    from native_tray_progress import show_shutdown_progress

    def operation(report):
        def progress(message):
            _LOG.info("shutdown stage: %s", message)
            report(message)
        try:
            shutdown_from_tray(target, progress=progress)
            _LOG.info("shutdown service STOPPED confirmed")
            return None
        except (ShutdownBlocked, ShutdownFailure) as exc:
            _LOG.warning("shutdown blocked/failed: %s", str(exc))
            return str(exc)
        except Exception as exc:
            _LOG.error("shutdown exception: %s", type(exc).__name__)
            return "종료 처리 중 오류가 발생했습니다. 트레이 로그를 확인하세요."

    try:
        error = show_shutdown_progress(operation)
    except Exception as exc:
        _LOG.error("shutdown progress exception: %s", type(exc).__name__)
        if getattr(exc, "operation_started", False):
            # Never issue a duplicate SCM/Agent stop after a message-loop failure.
            error = "종료 요청 후 진행창 표시가 중단됐습니다. 트레이 로그와 Windows 서비스 상태를 확인하세요."
        else:
            # Initialization failure must not prevent the actual stop request.
            error = operation(lambda message: None)
    if error is not None:
        _show_shutdown_result(error, failed=True)
        return False
    return True


def run_tray() -> None:
    _configure_logging()
    from version import VERSION
    _LOG.info("tray startup diagnostic revision=2026-11-03-install-gated version=%s", VERSION)
    from PIL import Image
    import pystray
    from pystray import MenuItem as Item
    from version import VERSION

    names = ("online", "offline", "unknown")
    images = {}
    for name in names:
        path = assets_dir() / ("pig-" + name + ".png")
        if not path.is_file():
            raise FileNotFoundError("Missing Pixel Pig state icon: " + str(path))
        images[name] = Image.open(path).convert("RGBA")

    done = threading.Event()
    icon = pystray.Icon("LKH_MCP", images["unknown"], "LKH MCP", menu=None)
    label = {"online": "Agent 연결됨", "offline": "Agent 연결 안 됨",
             "unknown": "상태 확인 불가"}

    def notice(message):
        try:
            icon.notify(message, "LKH MCP")
        except (OSError, NotImplementedError):
            pass

    def do_action(action):
        try:
            verdict = _read_state()
            if action in ("stop", "restart") and (
                    verdict["state"] == "unknown" or verdict["busy"] is not False):
                raise PermissionError("Agent state is unknown or busy")
            control_agent(action, busy=verdict["busy"] is True)
            notice("작업 요청됨; Agent 상태를 확인하세요.")
        except (PermissionError, OSError, RuntimeError):
            notice("Agent 작업 중 또는 상태 미확인: 관리자 페이지를 확인하세요.")

    shutdown_lock = threading.Lock()

    def do_start_server():
        if not shutdown_lock.acquire(blocking=False):
            notice("서버 시작 또는 종료 작업을 처리 중입니다.")
            return
        def perform():
            try:
                _start_server_with_feedback()
            finally:
                shutdown_lock.release()
        try:
            threading.Thread(target=perform, daemon=True, name="LKH-Tray-Start").start()
        except Exception:
            shutdown_lock.release()
            _show_shutdown_result("서버 시작 작업을 시작하지 못했습니다.", failed=True, action="서버 시작")

    def do_shutdown(target):
        _LOG.info("shutdown menu selected")
        if not shutdown_lock.acquire(blocking=False):
            notice("이미 서버 종료 요청을 처리 중입니다. 종료 진행창을 확인하세요.")
            return

        def perform():
            try:
                # Do not hold the Windows tray message loop inside a modal dialog.
                _LOG.info("shutdown confirmation displayed")
                if not _confirm_shutdown(target):
                    _LOG.info("shutdown confirmation cancelled")
                    return
                _LOG.info("shutdown confirmation accepted")
                if _shutdown_progress_window(target):
                    _LOG.info("shutdown tray closing")
                    done.set()
                    icon.stop()
            except Exception as exc:
                _LOG.error("shutdown worker exception: %s", type(exc).__name__)
                _show_shutdown_result("종료 처리 중 오류가 발생했습니다. 트레이 로그를 확인하세요.", failed=True)
            finally:
                shutdown_lock.release()
        try:
            threading.Thread(target=perform, daemon=True, name="LKH-Tray-Stop").start()
        except Exception as exc:
            shutdown_lock.release()
            _LOG.error("shutdown thread start failed: %s", type(exc).__name__)
            _show_shutdown_result("종료 작업을 시작하지 못했습니다. 트레이 로그를 확인하세요.", failed=True)

    def open_admin(icon, item):
        webbrowser.open(_admin_base() + "/admin", new=2)

    def update_state():
        previous = None
        while not done.wait(3):
            # The explicit shutdown worker owns its progress/result window until it
            # finishes. Outside that flow, an externally stopped server ends the tray.
            if shutdown_lock.locked():
                continue
            if _service_state() in ("stopped", "missing") and shutdown_lock.acquire(blocking=False):
                try:
                    done.set()
                    icon.stop()
                finally:
                    shutdown_lock.release()
                return
            current = status()
            if current != previous:
                icon.icon = images[current]
                icon.title = "LKH MCP " + VERSION + " - " + label[current]
                previous = current

    icon.menu = pystray.Menu(
        Item("관리자 페이지 열기", open_admin, default=True),
        Item("서버 시작", lambda i, t: do_start_server(),
             enabled=lambda item: _service_state() == "stopped"),
        pystray.Menu.SEPARATOR,
        Item("Agent 시작", lambda i, t: do_action("start")),
        Item("Agent 중지", lambda i, t: do_action("stop")),
        Item("Agent 재시작", lambda i, t: do_action("restart")),
        pystray.Menu.SEPARATOR,
        Item("종료", lambda i, t: do_shutdown("both")),
    )

    def setup(icon):
        initial = status()
        icon.icon = images[initial]
        icon.title = "LKH MCP " + VERSION + " - " + label[initial]
        icon.visible = True
        threading.Thread(target=update_state, name="LKH-Tray-Status", daemon=True).start()

    try:
        icon.run(setup=setup)
    finally:
        done.set()


def main() -> int:
    import argparse
    import ctypes
    from ctypes import wintypes
    from native_installation import allowed
    if os.name != "nt":
        raise RuntimeError("Native tray requires Windows")
    parser = argparse.ArgumentParser(description="Start LKH MCP and show its tray")
    parser.add_argument("--start-server", action="store_true", help="Start server and tray (default)")
    parser.add_argument("--tray-only", action="store_true", help="Login-session status tray only")
    args = parser.parse_args()
    _configure_logging()
    if not allowed():
        _show_shutdown_result("설치가 완료되지 않았거나 실패했습니다. 설치 프로그램을 정상 완료한 뒤 LKH MCP를 실행하세요.",
                              failed=True, action="실행")
        return 3
    if not args.tray_only and not _start_server_with_feedback():
        return 1
    if _service_state() in ("stopped", "missing"):
        return 0
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    mutex = kernel.CreateMutexW(None, False, "Local\\LKH_MCP_Tray")
    if not mutex:
        _show_shutdown_result("트레이 실행 상태를 확인하지 못했습니다.", failed=True, action="실행")
        return 1
    try:
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            return 0
        run_tray()
    finally:
        kernel.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
