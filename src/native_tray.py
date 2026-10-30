"""Separate Windows tray UI; never hosts MCP or exposes credentials.

Pixel Pig is generated from the approved branding image. The local tray
only reads loopback health + OS Scheduler state and invokes one fixed task.
The server continues if this user-session process exits.
"""
from __future__ import annotations

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
    port = os.getenv("LKH_NATIVE_ADMIN_PORT", "18081")
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Invalid native administrator port")
    return "http://127.0.0.1:" + port


def server_healthy() -> bool:
    try:
        with urllib.request.urlopen(_admin_base() + "/admin/healthz", timeout=2) as result:
            return result.status == 200
    except (OSError, ValueError):
        return False


def status() -> str:
    if not server_healthy():
        return "unknown"
    state = task_state()
    if state == "running":
        return "online"
    if state in ("ready", "disabled", "queued"):
        return "offline"
    return "unknown"


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
    label = {"online": "Agent 실행 중", "offline": "Agent 종료됨",
             "unknown": "상태 확인 불가"}

    def notice(message):
        try:
            icon.notify(message, "LKH MCP")
        except (OSError, NotImplementedError):
            pass

    def do_action(action):
        try:
            result = control_agent(action)
            notice("작업 요청됨; Agent 상태를 확인하세요.")
        except (PermissionError, OSError, RuntimeError) as exc:
            notice("작업 실행 실패: 설치 또는 Windows 작업 권한 확인")

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

    def close(icon, item):
        done.set()
        icon.stop()

    icon.menu = pystray.Menu(
        Item("관리자 페이지 열기", open_admin, default=True),
        pystray.Menu.SEPARATOR,
        Item("Agent 시작", lambda i, t: do_action("start")),
        Item("Agent 중지", lambda i, t: do_action("stop")),
        Item("Agent 재시작", lambda i, t: do_action("restart")),
        pystray.Menu.SEPARATOR,
        Item("트레이 종료 (MCP 서버는 유지)", close),
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
