"""Native Windows tray UI for the background LKH MCP server."""
from __future__ import annotations
import logging
import os
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit
from version import VERSION


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent.parent


def _dashboard_url() -> str:
    url = os.getenv("ADMIN_PUBLIC_ORIGIN", "https://mcp.gyangho.com").strip()
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment):
        raise ValueError("ADMIN_PUBLIC_ORIGIN은 HTTPS 호스트 URL이어야 합니다.")
    return url.rstrip("/") + "/admin"


def _is_healthy() -> bool:
    # Only probe the local anonymous liveness endpoint; never expose tokens.
    try:
        port = int(os.getenv("MCP_PORT", "8000"))
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=2
        ) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def run_with_tray(run_server) -> None:
    from PIL import Image
    import pystray
    from pystray import MenuItem as Item

    icon_path = _assets_dir() / "assets" / "lkh-mcp.png"
    if not icon_path.is_file():
        raise FileNotFoundError(f"Missing MCP icon: {icon_path}")
    image = Image.open(icon_path).convert("RGBA")

    def notify(icon, message):
        try:
            icon.notify(message, title="LKH MCP")
        except (NotImplementedError, OSError):
            logging.info("Tray notification: %s", message)

    def open_dashboard(icon, item):
        try:
            webbrowser.open(_dashboard_url(), new=2)
        except (OSError, ValueError):
            notify(icon, "대시보드 주소를 확인하세요.")

    def check_health(icon, item):
        notify(icon, "MCP 서버 응답 정상" if _is_healthy() else "헬스체크 실패: 로컬 서버 상태 확인")

    def quit_server(icon, item):
        from runtime_state import telemetry
        if telemetry()["active_count"]:
            notify(icon, "실행 중인 도구가 있어 서버 종료를 취소했습니다.")
            return
        logging.info("MCP shutdown requested from tray")
        icon.stop()

    def serve(icon):
        try:
            run_server()
        except BaseException:
            logging.exception("MCP server stopped unexpectedly")
            notify(icon, "MCP 서버 실행 실패. 로그를 확인하세요.")
        finally:
            icon.stop()

    menu = pystray.Menu(
        Item("대시보드 열기", open_dashboard, default=True),
        Item("상태 확인", check_health),
        pystray.Menu.SEPARATOR,
        Item("종료", quit_server),
    )
    tray = pystray.Icon("LKH_MCP", image, f"LKH MCP v{VERSION}", menu)
    thread = threading.Thread(target=serve, args=(tray,), daemon=True, name="LKH-MCP-server")

    def setup(icon):
        icon.visible = True
        thread.start()

    # pystray's GUI loop runs on the main thread; MCP runs in a worker.
    tray.run(setup=setup)
