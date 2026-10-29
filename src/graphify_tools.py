"""Allowlisted, bounded access to local Graphify CLI knowledge graphs.

Only preconfigured project roots and fixed Graphify subcommands can be called.
Graphify must be installed locally as the official graphifyy package.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_GRAPH_REL = Path("graphify-out") / "graph.json"
_UPDATE_LOCK = threading.Lock()


def _project_roots() -> dict[str, Path]:
    """Parse GRAPHIFY_PROJECTS='ITAM=C:/path;OTHER=D:/path'. Fail closed."""
    raw = os.environ.get("GRAPHIFY_PROJECTS", "").strip()
    if not raw:
        return {}
    roots: dict[str, Path] = {}
    for entry in raw.split(";"):
        if not entry or "=" not in entry:
            raise ValueError("GRAPHIFY_PROJECTS 형식: ITAM=C:/Projects/ITAM;OTHER=D:/Projects/OTHER")
        name, location = entry.split("=", 1)
        name, location = name.strip(), location.strip()
        if not _NAME_RE.fullmatch(name) or not location:
            raise ValueError("GRAPHIFY_PROJECTS 프로젝트 이름/경로가 유효하지 않습니다.")
        p = Path(location).expanduser()
        if not p.is_absolute():
            raise ValueError("GRAPHIFY_PROJECTS에는 절대 경로만 허용됩니다.")
        if name in roots:
            raise ValueError("GRAPHIFY_PROJECTS에 중복 프로젝트 이름이 있습니다.")
        roots[name] = p.resolve()
        if len(roots) > 10:
            raise ValueError("Graphify 프로젝트는 최대 10개까지 등록할 수 있습니다.")
    return roots


def _get_project(name: str) -> tuple[Path, Path]:
    roots = _project_roots()
    if not isinstance(name, str) or name not in roots:
        raise ValueError("허용되지 않은 프로젝트입니다. graphify_list_projects로 등록 목록을 확인하세요.")
    root = roots[name]
    if not root.is_dir():
        raise FileNotFoundError("등록된 프로젝트 폴더가 존재하지 않습니다.")
    graph = root / _GRAPH_REL
    if not graph.is_file():
        raise FileNotFoundError("graphify-out/graph.json이 없습니다. PC에서 먼저 graphify로 그래프를 생성하세요.")
    if not graph.resolve().is_relative_to(root):
        raise ValueError("그래프 경로가 프로젝트 외부를 가리킵니다.")
    return root, graph


def _graphify_binary() -> str:
    configured = os.environ.get("GRAPHIFY_EXECUTABLE", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise FileNotFoundError("GRAPHIFY_EXECUTABLE은 기존 실행 파일의 절대 경로여야 합니다.")
        binary = str(path.resolve())
    else:
        binary = shutil.which("graphify")
        if not binary:
            raise FileNotFoundError("Graphify CLI를 찾을 수 없습니다. 공식 graphifyy 설치와 PATH를 확인하세요.")
    if os.name == "nt" and Path(binary).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        raise ValueError("Graphify 실행 파일은 .exe 형태를 사용하세요 (.cmd/.bat/.ps1 불허).")
    return binary


def _safe_text(value: str, label: str, *, max_length: int = 250) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{label}: 1~{max_length}자 문자열이 필요합니다.")
    result = value.strip()
    if result.startswith("-") or any(ord(c) < 32 for c in result):
        raise ValueError(f"{label}: 옵션 형태 또는 제어 문자는 허용되지 않습니다.")
    return result


def _run_graphify(project: str, args: list[str], *, timeout: int) -> dict[str, Any]:
    root, graph = _get_project(project)
    binary = _graphify_binary()
    # Keep Oracle credentials, OAuth tokens and unrelated secrets out of the child.
    # Graphify needs only basic Windows/Python process and user-cache variables.
    safe_env_keys = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
        "TMPDIR", "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH",
        "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "LANG", "LC_ALL",
        "PYTHONIOENCODING",
    }
    env = {k: v for k, v in os.environ.items() if k.upper() in safe_env_keys}
    env["GRAPHIFY_BACKEND"] = "none"
    env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    env["GRAPHIFY_NO_TIPS"] = "1"
    try:
        proc = subprocess.run(
            [binary, *args], cwd=str(root), env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, shell=False, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"Graphify 실행 시간이 {timeout}초를 초과했습니다. 대형 프로젝트는 로컬에서 갱신하세요.") from exc
    except OSError as exc:
        raise RuntimeError(f"Graphify CLI 실행 실패: {type(exc).__name__}") from exc
    limit = 16_000
    stdout = proc.stdout[:limit]
    stderr = proc.stderr[-2000:]
    if len(proc.stdout) > limit:
        stdout += "\n... [출력 길이 제한으로 일부 생략]"
    return {
        "project": project,
        "operation": args[0],
        "success": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output": stdout,
        "error": stderr,
        "graph_last_modified": graph.stat().st_mtime if graph.exists() else None,
    }


def register_graphify_tools(mcp: Any) -> None:
    """Register bounded Graphify tools on the existing LKH MCP server."""

    @mcp.tool()
    def graphify_list_projects() -> dict:
        """List configured local Graphify projects and graph readiness; no absolute paths."""
        roots = _project_roots()
        return {"projects": [
            {"name": name, "graph_exists": (root / _GRAPH_REL).is_file(),
             "directory_exists": root.is_dir()}
            for name, root in sorted(roots.items())
        ], "update_enabled": os.environ.get("GRAPHIFY_ALLOW_UPDATE", "false").lower() == "true"}

    @mcp.tool()
    def graphify_query(project: str, question: str, budget: int = 2000, depth_first: bool = False) -> dict:
        """Read-only Graphify code-graph query. Use concrete function/module keywords; not full-text search."""
        question = _safe_text(question, "question", max_length=300)
        if not isinstance(budget, int) or not 200 <= budget <= 4000:
            raise ValueError("budget은 200~4000 사이 정수여야 합니다.")
        if not isinstance(depth_first, bool):
            raise ValueError("depth_first는 bool이어야 합니다.")
        args = ["query", question, "--budget", str(budget)]
        if depth_first:
            args.append("--dfs")
        return _run_graphify(project, args, timeout=45)

    @mcp.tool()
    def graphify_explain(project: str, concept: str) -> dict:
        """Read-only explanation of a named node, module, class or function."""
        return _run_graphify(project, ["explain", _safe_text(concept, "concept")], timeout=45)

    @mcp.tool()
    def graphify_path(project: str, source: str, target: str) -> dict:
        """Read-only shortest relationship path between two named graph nodes."""
        return _run_graphify(project, ["path", _safe_text(source, "source"), _safe_text(target, "target")], timeout=45)

    @mcp.tool()
    def graphify_update(project: str) -> dict:
        """Incrementally refresh added/modified/deleted code in an existing graph. Requires explicit local opt-in. Updates generated graph files, not project source code."""
        if os.environ.get("GRAPHIFY_ALLOW_UPDATE", "false").lower() != "true":
            raise PermissionError("그래프 갱신이 비활성화되어 있습니다. 로컬 .env에서 GRAPHIFY_ALLOW_UPDATE=true로 승인하세요.")
        if not _UPDATE_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 Graphify 그래프 갱신이 진행 중입니다.")
        try:
            return _run_graphify(project, ["update", "."], timeout=120)
        finally:
            _UPDATE_LOCK.release()
