"""Opt-in local Git tools for the existing LKH MCP Portal.

GitHub repository editing is done by the separate connected GitHub plugin.
These tools only inspect explicitly allowed local checkouts and optionally
push an already committed clean HEAD. No arbitrary shell or git commands.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from graphify_tools import _project_roots

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}$")


def _allowed() -> dict[str, str]:
    raw = os.getenv("GIT_ALLOWED_REPOS", "").strip()
    if not raw:
        return {}
    result: dict[str, str] = {}
    for entry in raw.split(";"):
        if "=" not in entry:
            raise ValueError("GIT_ALLOWED_REPOS 형식: ITAM=owner/ITAM;LKH_MCP=owner/LKH_MCP")
        name, repo = (part.strip() for part in entry.split("=", 1))
        if not _NAME.fullmatch(name) or not _REPO.fullmatch(repo) or name in result:
            raise ValueError("GIT_ALLOWED_REPOS에 유효하지 않거나 중복된 항목이 있습니다.")
        result[name] = repo
        if len(result) > 10:
            raise ValueError("허용 Git 프로젝트는 최대 10개입니다.")
    return result


def _project(name: str) -> tuple[Path, str]:
    roots = _project_roots()
    allowed = _allowed()
    if not isinstance(name, str) or name not in roots or name not in allowed:
        raise ValueError("허용되지 않은 프로젝트입니다. git_list_projects를 확인하세요.")
    root = roots[name]
    if not root.is_dir() or not (root / ".git").exists():
        raise FileNotFoundError("등록한 폴더에 Git 작업 트리가 없습니다.")
    return root, allowed[name]


def _executable() -> str:
    configured = os.getenv("GIT_EXECUTABLE", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute() or not path.is_file():
            raise FileNotFoundError("GIT_EXECUTABLE은 기존 실행 파일의 절대 경로여야 합니다.")
        exe = str(path.resolve())
    else:
        exe = shutil.which("git")
        if not exe:
            raise FileNotFoundError("Git을 PATH에서 찾을 수 없습니다.")
    if os.name == "nt" and Path(exe).suffix.lower() in (".cmd", ".bat", ".ps1"):
        raise ValueError("Windows에서는 Git .exe만 허용합니다.")
    return exe


def _env() -> dict[str, str]:
    # Avoid forwarding Oracle passwords, API tokens and arbitrary secrets.
    keep = {
        "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
        "USERPROFILE", "HOME", "HOMEDRIVE", "HOMEPATH",
        "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC",
        "SYSTEMDRIVE", "LANG", "LC_ALL", "SSH_AUTH_SOCK",
    }
    env = {key: val for key, val in os.environ.items() if key.upper() in keep}
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_NO_REPLACE_OBJECTS="1")
    return env


def _git(root: Path, *args: str, timeout: int = 15) -> str:
    try:
        proc = subprocess.run(
            [_executable(), *args], cwd=str(root), env=_env(),
            shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Git 명령 실행 실패 또는 시간 초과") from exc
    if proc.returncode:
        # Avoid returning stderr that might contain credentials or remote URLs.
        raise RuntimeError(f"Git {args[0]} 실패(exit={proc.returncode}). PC에서 Git 인증/브랜치 설정을 확인하세요.")
    return proc.stdout


def _verified(name: str) -> tuple[Path, str]:
    root, expected = _project(name)
    top = Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve()
    if top != root.resolve():
        raise ValueError("Git 루트가 등록한 프로젝트와 다릅니다.")
    origin = _git(root, "remote", "get-url", "origin").strip()
    escaped = re.escape(expected)
    pattern = (rf"(?:https://github\.com/{escaped}(?:\.git)?|"
               rf"git@github\.com:{escaped}(?:\.git)?|"
               rf"ssh://git@github\.com/{escaped}(?:\.git)?)")
    if not re.fullmatch(pattern, origin, re.IGNORECASE):
        raise ValueError("origin URL이 GIT_ALLOWED_REPOS의 GitHub 저장소와 다릅니다.")
    return root, expected


def _head(root: Path) -> tuple[str, str]:
    branch = _git(root, "symbolic-ref", "--short", "HEAD").strip()
    if (not _BRANCH.fullmatch(branch) or ".." in branch or "//" in branch
            or branch.startswith(".") or branch.endswith(("/", ".", ".lock"))):
        raise ValueError("지원되지 않는 Git 브랜치 이름입니다.")
    head = _git(root, "rev-parse", "HEAD").strip()
    if not _SHA.fullmatch(head):
        raise ValueError("HEAD SHA 검증 실패")
    return branch, head


def register_git_tools(mcp: Any) -> None:
    """Register bounded local Git diagnostics and an opt-in committed push."""

    @mcp.tool()
    def git_list_projects() -> dict:
        """List configured local Git checkouts and allowed GitHub repositories; no filesystem paths."""
        roots, allowed = _project_roots(), _allowed()
        return {"projects": [
            {"project": name, "github_repo": repo,
             "directory_exists": name in roots and roots[name].is_dir(),
             "git_exists": name in roots and (roots[name] / ".git").exists()}
            for name, repo in sorted(allowed.items())
        ], "push_enabled": os.getenv("GIT_ALLOW_PUSH", "false").lower() == "true",
           "commit_enabled": os.getenv("GIT_ALLOW_COMMIT", "false").lower() == "true"}

    @mcp.tool()
    def git_status(project: str) -> dict:
        """Read local branch, commit SHA and pending file changes, without contacting GitHub."""
        root, repo = _verified(project)
        branch, sha = _head(root)
        changes = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        return {"project": project, "github_repo": repo, "branch": branch,
                "head": sha, "clean": not bool(changes.strip()),
                "working_tree": changes[:12000], "truncated": len(changes) > 12000,
                "note": "로컬 Git 상태입니다. GitHub 원격 최신 여부는 fetch하지 않았습니다."}

    @mcp.tool()
    def git_diff(project: str, staged: bool = False) -> dict:
        """Read bounded local source-code diff; results might contain sensitive content."""
        if not isinstance(staged, bool):
            raise ValueError("staged는 bool이어야 합니다.")
        root, repo = _verified(project)
        cmd = ["diff", "--no-ext-diff", "--no-textconv"]
        if staged:
            cmd.append("--cached")
        cmd += ["--", "."]
        diff = _git(root, *cmd, timeout=30)
        return {"project": project, "github_repo": repo, "staged": staged,
                "diff": diff[:18000], "truncated": len(diff) > 18000}

    @mcp.tool()
    def git_push(project: str, expected_head: str) -> dict:
        """Push an already committed, clean local HEAD to its same-name GitHub origin branch, never force. Opt-in required. Does not stage, commit, pull or modify code."""
        if os.getenv("GIT_ALLOW_PUSH", "false").lower() != "true":
            raise PermissionError("GIT_ALLOW_PUSH=true로 명시적으로 허용해야 합니다.")
        if not isinstance(expected_head, str) or not _SHA.fullmatch(expected_head):
            raise ValueError("git_status가 반환한 HEAD SHA 40자리가 필요합니다.")
        root, repo = _verified(project)
        branch, sha = _head(root)
        if sha.lower() != expected_head.lower():
            raise RuntimeError("확인 후 HEAD가 변경되었습니다. git_status를 다시 확인하세요.")
        if _git(root, "status", "--porcelain=v1", "--untracked-files=normal").strip():
            raise RuntimeError("미커밋 변경사항이 존재합니다. PC에서 검토·커밋한 뒤 다시 시도하세요.")
        # No --force, remote/branch user input, or credential output.
        _git(root, "push", "--porcelain", "origin", f"HEAD:refs/heads/{branch}", timeout=90)
        return {"success": True, "project": project, "github_repo": repo,
                "branch": branch, "pushed_head": sha}
