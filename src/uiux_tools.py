"""Read-only MCP tools wrapping the official UI UX Pro Max Python search engine.

Copy alongside the existing LKH_MCP/server.py, then call
register_uiux_tools(mcp) before mcp.run(...).
The upstream repo lives in vendor/ui-ux-pro-max-skill (no automatic download).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT = (
    Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    / "vendor"
    / "ui-ux-pro-max-skill"
    / "src"
    / "ui-ux-pro-max"
    / "scripts"
    / "search.py"
)

DOMAINS = frozenset(
    ("style", "color", "chart", "landing", "product", "ux", "typography",
     "google-fonts", "icons", "gsap", "react", "web")
)
STACKS = frozenset(
    ("react", "nextjs", "vue", "svelte", "astro", "swiftui", "react-native",
     "flutter", "nuxtjs", "nuxt-ui", "html-tailwind", "shadcn",
     "jetpack-compose", "threejs", "angular", "laravel", "javafx", "wpf",
     "winui", "avalonia", "uno", "uwp")
)


def _check_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        raise ValueError("query는 1~300자여야 합니다.")
    if query.lstrip().startswith("-"):
        raise ValueError("query는 '-'로 시작할 수 없습니다.")
    return query.strip()


def _execute(*args: str) -> dict[str, Any]:
    if not SCRIPT.is_file():
        raise RuntimeError(
            "원본 UI UX Pro Max 검색 파일을 찾을 수 없습니다. "
            "vendor/ui-ux-pro-max-skill/src/ui-ux-pro-max/scripts/search.py 경로를 확인하세요."
        )
    # Do not accept a command string or use shell=True; never persist files.
    if getattr(sys, "frozen", False):
        interpreter = os.getenv("UIUX_PYTHON_EXECUTABLE", "").strip()
        if not interpreter or not Path(interpreter).is_absolute() or not Path(interpreter).is_file():
            raise RuntimeError("EXE 모드에서는 UIUX_PYTHON_EXECUTABLE에 python.exe 절대 경로를 지정하세요.")
    else:
        interpreter = os.getenv("UIUX_PYTHON_EXECUTABLE") or sys.executable
    cmd = [interpreter, str(SCRIPT), *args, "--json"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SCRIPT.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=40,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("UI UX Pro Max 검색 시간이 40초를 초과했습니다.") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("UI UX Pro Max Python 실행 파일을 찾을 수 없습니다. UIUX_PYTHON_EXECUTABLE 또는 가상환경 Python 경로를 확인하세요.") from exc
    except OSError as exc:
        raise RuntimeError("UI UX Pro Max 검색 프로세스 시작에 실패했습니다. 실행 파일과 접근 권한을 확인하세요.") from exc
    if result.returncode:
        raise RuntimeError(
            f"UI UX Pro Max 검색 오류 (exit={result.returncode}): "
            f"{result.stderr[-1000:]}"
        )
    if len(result.stdout) > 600_000:
        raise RuntimeError("검색 결과가 너무 큽니다. 검색어를 구체화하세요.")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("원본 검색기의 JSON 결과 해석에 실패했습니다.") from exc
    if not isinstance(data, dict):
        raise RuntimeError("원본 검색 결과가 JSON 객체가 아닙니다.")
    return data


def register_uiux_tools(mcp: Any) -> None:
    @mcp.tool()
    def uiux_diagnostics() -> dict:
        """Read-only UI UX Pro Max installation check; no file paths or tokens exposed."""
        frozen = bool(getattr(sys, "frozen", False))
        interpreter = (os.environ.get("UIUX_PYTHON_EXECUTABLE", "").strip()
                       if frozen else (os.environ.get("UIUX_PYTHON_EXECUTABLE") or sys.executable))
        python_ok = bool(interpreter and Path(interpreter).is_file())
        ready = SCRIPT.is_file() and python_ok
        return {"ready": ready, "search_script_found": SCRIPT.is_file(),
                "python_interpreter_available": python_ok, "packaged_exe": frozen,
                "hint": ("정상" if ready else
                         "UI UX Pro Max vendor 서브모듈과 Python 실행 경로를 확인하세요.")}

    """Register only UI/UX-domain tools on the existing MCPServer instance."""

    @mcp.tool()
    def uiux_search(query: str, domain: str = "", max_results: int = 3) -> dict:
        """Only for UI/UX requests: search official style/color/UX/chart/typography/icon etc. CSV guidance. Blank domain uses upstream auto-detection. Never use for database or general questions."""
        query = _check_query(query)
        if domain and domain not in DOMAINS:
            raise ValueError(f"지원하지 않는 domain입니다: {domain}. 사용 가능: {', '.join(sorted(DOMAINS))}")
        if not isinstance(max_results, int) or not 1 <= max_results <= 10:
            raise ValueError("max_results는 1~10 사이 정수여야 합니다.")
        args = [query, "--max-results", str(max_results)]
        if domain:
            args.extend(("--domain", domain))
        return _execute(*args)

    @mcp.tool()
    def uiux_stack_guidelines(query: str, stack: str, max_results: int = 3) -> dict:
        """Only for UI/UX implementation: search official stack-specific interface guidance (React, WPF, Next.js, etc.). Never use for unrelated programming or DB queries."""
        query = _check_query(query)
        if stack not in STACKS:
            return {"error": {"code": "UNSUPPORTED_STACK",
                              "message": f"지원하지 않는 stack입니다: {stack}. 일반 HTML/CSS는 uiux_search를 사용하세요.",
                              "supported_stacks": sorted(STACKS),
                              "suggested_tool": "uiux_search" if stack == "html" else "uiux_stack_guidelines"}}
        if not isinstance(max_results, int) or not 1 <= max_results <= 10:
            raise ValueError("max_results는 1~10 사이 정수여야 합니다.")
        return _execute(query, "--stack", stack, "--max-results", str(max_results))

    @mcp.tool()
    def uiux_generate_design_system(query: str, project_name: str = "My Project") -> dict:
        """Only for UI/UX design planning: generate a coherent design system (style, palette, typography, layouts, accessibility) from the official database. Read-only; does not write files."""
        query = _check_query(query)
        if not isinstance(project_name, str) or not project_name.strip() or len(project_name) > 100:
            raise ValueError("project_name은 1~100자여야 합니다.")
        return _execute(query, "--design-system", "--project-name", project_name.strip())
