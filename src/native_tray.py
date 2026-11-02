"""Separate Windows tray UI; never hosts MCP or exposes credentials.

Pixel Pig is generated from the approved branding image. The local tray
reads the server's loopback authenticated-heartbeat status and invokes one fixed task.
The server continues if this user-session process exits.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from native_task_control import control_agent, task_state


def assets_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"


def _admin_base() -> str:
    port = os.getenv("LKH_NATIVE_ADMIN_PORT", "8001")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid native administrator port")
    return "http://127.0.0.1:" + port


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


def _installed_service_binary() -> Path:
    """Resolve only the adjacent, installer-owned SCM controller executable."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Native Installer tray is required to stop the service")
    service = (Path(sys.executable).resolve().parent.parent /
               "LKH-MCP-Service" / "LKH-MCP-Service.exe")
    if not service.is_file():
        raise RuntimeError("LKH-MCP-Service.exe is not installed")
    return service


def _request_scm_stop(executable: Path) -> None:
    """Request an OS-authorized stop through UAC, never an unauthenticated HTTP API."""
    import ctypes
    if os.name != "nt":
        raise RuntimeError("Windows SCM is required")
    # The executable and command are fixed: no caller-supplied shell or service name.
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", str(executable), "stop", str(executable.parent), 1)
    if int(result) <= 32:
        raise PermissionError("Windows UAC denied or could not launch the service stop")
    # ShellExecuteW acknowledges launch only, not completed service shutdown.


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




def shutdown_from_tray(target: str) -> None:
    """Safely request shutdown using Windows SCM privileges and Task Scheduler ACLs.

    The tray has no administrator browser cookie; it must never bypass session/CSRF.
    """
    if target not in ("server", "both"):
        raise ValueError("Unknown fixed shutdown target")
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
            scheduler = task_state()
        except Exception as exc:
            raise ShutdownFailure("Agent 작업 스케줄러 상태를 확인하지 못해 서버 종료를 요청하지 않았습니다.\n"
                                  "작업 스케줄러의 LKH-Codex-Agent 등록 상태와 권한을 확인하세요.") from exc
        if scheduler not in ("running", "ready", "disabled"):
            raise ShutdownFailure("Agent가 대기 중인지 확인할 수 없어 서버 종료를 요청하지 않았습니다.\n"
                                  "작업 스케줄러의 LKH-Codex-Agent 상태를 확인한 뒤 다시 시도하세요.")
        if scheduler == "running":
            try:
                control_agent("stop", busy=False)
                _wait_for_agent_stop()
            except Exception as exc:
                raise ShutdownFailure("Agent 중지에 실패해 서버 종료를 요청하지 않았습니다.\n"
                                      "작업 스케줄러의 LKH-Codex-Agent 상태와 권한을 확인하세요.") from exc
    try:
        _request_scm_stop(service_binary)
    except (OSError, RuntimeError) as exc:
        raise ShutdownFailure("Windows 서비스 종료 프로그램을 실행하지 못했습니다.\n"
                              "UAC 승인이 취소되었거나 실행 권한이 없을 수 있습니다. 다시 시도하세요.") from exc
    try:
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
                                            0x4 | 0x30 | 0x100) == 6


def _show_shutdown_result(message: str, *, failed: bool) -> None:
    import ctypes
    # A modal result stays visible even when Windows tray notifications are disabled.
    ctypes.windll.user32.MessageBoxW(
        None, message, "LKH MCP 종료 실패" if failed else "LKH MCP 종료 요청",
        (0x10 if failed else 0x40) | 0x10000 | 0x40000)


def _shutdown_with_feedback(target: str) -> bool:
    try:
        shutdown_from_tray(target)
    except (ShutdownBlocked, ShutdownFailure) as exc:
        _show_shutdown_result(str(exc), failed=True)
    except Exception:
        # Never expose raw OS/COM errors or paths in the UI.
        _show_shutdown_result("종료 처리 중 오류가 발생했습니다. Windows 서비스와 Agent 상태를 확인하세요.",
                              failed=True)
    else:
        return True  # SCM STOPPED was observed; the caller may close the tray.
    return False


def run_tray() -> None:
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

    def do_shutdown(target):
        if not shutdown_lock.acquire(blocking=False):
            notice("이미 서버 종료 요청을 처리 중입니다.")
            return
        owns_lock = True
        try:
            if not _confirm_shutdown(target):
                return

            def perform():
                try:
                    if _shutdown_with_feedback(target):
                        done.set()
                        icon.stop()
                except Exception:
                    notice("종료 처리 실패: 서비스와 트레이 상태를 확인하세요.")
                finally:
                    shutdown_lock.release()
            threading.Thread(target=perform, daemon=True, name="LKH-Tray-Stop").start()
            owns_lock = False
        except (OSError, RuntimeError):
            notice("Windows 종료 확인창을 표시할 수 없습니다.")
        finally:
            if owns_lock:
                shutdown_lock.release()

    def open_admin(icon, item):
        webbrowser.open(_admin_base() + "/admin", new=2)

    def update_state():
        previous = None
        while not done.wait(3):
            current = status()
            if current != previous:
                icon.icon = images[current]
                icon.title = "LKH MCP " + VERSION + " - " + label[current]
                previous = current

    icon.menu = pystray.Menu(
        Item("관리자 페이지 열기", open_admin, default=True),
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


if __name__ == "__main__":
    if os.name != "nt":
        raise RuntimeError("Native tray requires Windows")
    run_tray()
