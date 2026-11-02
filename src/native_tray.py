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


def shutdown_from_tray(target: str) -> None:
    """Safely request shutdown using Windows SCM privileges and Task Scheduler ACLs.

    The tray has no administrator browser cookie; it must never bypass session/CSRF.
    """
    if target not in ("server", "both"):
        raise ValueError("Unknown fixed shutdown target")
    verdict = _read_state()
    if verdict["state"] not in ("online", "offline") or verdict["busy"] is not False:
        raise PermissionError("Cannot confirm that all Codex tasks are idle")
    service_binary = _installed_service_binary()
    if target == "both":
        scheduler = task_state()
        if scheduler not in ("running", "ready", "disabled"):
            raise RuntimeError("Agent scheduler state is unknown")
        if scheduler == "running":
            control_agent("stop", busy=False)
    _request_scm_stop(service_binary)


def _confirm_shutdown(target: str) -> bool:
    import ctypes
    name = "MCP 서버와 Agent" if target == "both" else "MCP 서버"
    message = (name + "를 종료하시겠습니까?\n"
               "현재 작업이 실행 중이면 중단되며, Windows 관리자(UAC) 승인이 필요합니다.\n"
               "취소하면 종료하지 않습니다.")
    # MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2 (No)
    return ctypes.windll.user32.MessageBoxW(None, message, "LKH MCP 종료 확인",
                                            0x4 | 0x30 | 0x100) == 6


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
                    shutdown_from_tray(target)
                    notice("Windows 서비스 종료 요청됨. 실제 중지 상태를 확인하세요.")
                except (PermissionError, OSError, RuntimeError, ValueError):
                    notice("종료 실패 또는 UAC 취소: 서비스 권한과 Agent 작업을 확인하세요.")
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
