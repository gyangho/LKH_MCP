"""Auditable, opt-in local Git staging and commits for LKH MCP.

The assistant reviews a bounded staged patch and writes a commit message.
Only explicitly selected paths may be staged. Before committing, the local
HEAD and SHA-256 of the *entire staged diff* must still match the preview.
No arbitrary Git commands, shell execution, pull, checkout or force push.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from git_tools import _git, _head, _verified

_COMMIT_LOCK = threading.Lock()
_DIFF_MAX = 48_000
_MAX_PATHS = 30
_SHA = re.compile(r"^[a-fA-F0-9]{40}$")
_DIGEST = re.compile(r"^[a-fA-F0-9]{64}$")
_BLOCKED_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".p8", ".jks", ".keystore", ".sqlite", ".db")
_BLOCKED_NAMES = {
    ".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "known_hosts",
    "credentials", "credentials.json", "secrets.json", "secrets.yml",
    "secrets.yaml", "token", "token.json", "config.json.secret",
}
_BLOCKED_DIRS = {".git", ".ssh", ".aws", ".azure", ".kube", "node_modules", ".venv"}


def _enabled() -> None:
    if os.getenv("GIT_ALLOW_COMMIT", "false").strip().lower() != "true":
        raise PermissionError("원격 Git 커밋은 비활성화되어 있습니다. 로컬 .env에 GIT_ALLOW_COMMIT=true를 설정하세요.")


def _safe_path(root: Path, name: str) -> str:
    if not isinstance(name, str) or not name or len(name) > 240:
        raise ValueError("파일 경로는 1~240자의 저장소 상대 경로여야 합니다.")
    if ("\\" in name or "\x00" in name or "\n" in name or "\r" in name
            or name.startswith(("-", "/", "~")) or ":" in name):
        raise ValueError("경로는 상대 POSIX 경로만 허용합니다.")
    parts = name.split("/")
    if any(not part or part in (".", "..") for part in parts):
        raise ValueError("디렉터리 전체/상위 경로 또는 빈 경로는 허용하지 않습니다.")
    lowered = [part.lower() for part in parts]
    filename = lowered[-1]
    if (any(part in _BLOCKED_DIRS for part in lowered)
            or filename in _BLOCKED_NAMES or filename.startswith(".env.")
            or filename.endswith(_BLOCKED_SUFFIXES)
            or any(token in filename for token in ("password", "private_key", "secret_key", "access_token"))):
        raise ValueError("인증 정보·비밀 파일로 추정되는 경로는 원격 스테이징/커밋할 수 없습니다.")
    full = root.joinpath(*parts)
    # On Windows a symlink/junction may escape the project even if the text path is relative.
    if not full.resolve().is_relative_to(root.resolve()):
        raise ValueError("경로가 등록된 프로젝트 밖으로 벗어납니다.")
    for parent in [full, *list(full.parents)[:-1]]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("심볼릭 링크 경로는 허용하지 않습니다.")
    if full.exists() and (not full.is_file() or full.is_symlink()):
        raise ValueError("디렉터리나 심볼릭 링크는 직접 스테이징할 수 없습니다.")
    if full.exists() and full.stat().st_size > 4_000_000:
        raise ValueError("4MB를 초과하는 파일은 PC에서 직접 검토/커밋하세요.")
    return name


def _staged(root: Path) -> tuple[str, list[str]]:
    patch = _git(root, "diff", "--cached", "--no-ext-diff", "--no-textconv", "--binary", "--", ".", timeout=35)
    paths = _git(root, "diff", "--cached", "--name-only", "-z", "--", ".", timeout=20)
    names = [item for item in paths.split("\x00") if item]
    if not names or not patch.strip():
        raise ValueError("스테이징된 변경사항이 없습니다. 먼저 git_stage_paths를 사용하세요.")
    if len(names) > _MAX_PATHS:
        raise ValueError("원격 커밋은 최대 30개 파일만 지원합니다. PC에서 직접 커밋하세요.")
    for item in names:
        _safe_path(root, item)
    if len(patch.encode("utf-8")) > _DIFF_MAX:
        raise ValueError("스테이징된 diff가 48KB를 초과합니다. 전체 내용을 검토할 수 없어 원격 커밋을 거부합니다.")
    return patch, names


def _snapshot(root: Path) -> dict:
    branch, head = _head(root)
    patch, paths = _staged(root)
    return {
        "branch": branch,
        "head": head,
        "diff_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "paths": paths,
        "patch": patch,
    }


def register_git_commit_tools(mcp: Any) -> None:
    """Add an AI-assisted review -> message -> commit workflow to the local Git bridge."""

    @mcp.tool()
    def git_stage_paths(project: str, paths: list[str], expected_head: str) -> dict:
        """Stage ONLY explicitly chosen repository-relative files. Requires GIT_ALLOW_COMMIT=true. Never stages all files, ignores credential-like paths and refuses pre-existing staged changes."""
        _enabled()
        if not isinstance(paths, list) or not 1 <= len(paths) <= _MAX_PATHS:
            raise ValueError("paths에는 1~30개 파일을 명시해야 합니다.")
        if not isinstance(expected_head, str) or not _SHA.fullmatch(expected_head):
            raise ValueError("git_status가 반환한 40자리 expected_head가 필요합니다.")
        if not _COMMIT_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 커밋 관련 작업이 진행 중입니다.")
        try:
            root, repo = _verified(project)
            branch, head = _head(root)
            if head.lower() != expected_head.lower():
                raise RuntimeError("브랜치 HEAD가 변경되었습니다. git_status를 다시 실행하세요.")
            if _git(root, "diff", "--cached", "--name-only", "--", ".").strip():
                raise RuntimeError("이미 스테이징된 파일이 있습니다. PC에서 먼저 처리하거나 인덱스를 정리하세요.")
            selected = [_safe_path(root, p) for p in paths]
            if len(set(selected)) != len(selected):
                raise ValueError("paths에 중복된 파일이 있습니다.")
            # A missing path is only valid for a deletion of a previously tracked file.
            for path in selected:
                if not root.joinpath(*path.split("/")).exists():
                    _git(root, "ls-files", "--error-unmatch", "--", path)
            _git(root, "add", "-A", "--", *selected, timeout=40)
            snapshot = _snapshot(root)
            return {"project": project, "github_repo": repo, "branch": branch,
                    "head": head, "staged_files": snapshot["paths"],
                    "next_step": "git_preview_commit으로 전체 diff를 읽고 커밋 메시지를 작성하세요."}
        finally:
            _COMMIT_LOCK.release()

    @mcp.tool()
    def git_preview_commit(project: str) -> dict:
        """Read the COMPLETE staged patch, its hash and HEAD. The assistant must review these contents before writing the commit subject/body."""
        root, repo = _verified(project)
        state = _snapshot(root)
        return {"project": project, "github_repo": repo, **state,
                "instruction": "이 diff를 검토하고 의미 있는 커밋 제목/본문을 작성한 뒤 동일한 HEAD와 diff_sha256으로 git_commit을 호출하세요."}

    @mcp.tool()
    def git_commit(project: str, expected_head: str, expected_diff_sha256: str,
                   subject: str, body: str = "") -> dict:
        """Commit the EXACT staged diff already shown by git_preview_commit. ChatGPT writes the message. Requires explicit user request, GIT_ALLOW_COMMIT=true, and unchanged SHA-256/HEAD; does not push."""
        _enabled()
        if not isinstance(expected_head, str) or not _SHA.fullmatch(expected_head):
            raise ValueError("expected_head는 preview 결과의 HEAD SHA여야 합니다.")
        if not isinstance(expected_diff_sha256, str) or not _DIGEST.fullmatch(expected_diff_sha256):
            raise ValueError("expected_diff_sha256는 preview 결과의 SHA-256이어야 합니다.")
        if (not isinstance(subject, str) or not subject.strip()
                or len(subject) > 100 or any(c in subject for c in "\r\n\x00")
                or any(ord(c) < 32 for c in subject)):
            raise ValueError("커밋 제목은 제어 문자 없이 1~100자여야 합니다.")
        if (not isinstance(body, str) or len(body) > 1500 or "\x00" in body
                or "\r" in body or any(ord(c) < 32 and c != "\n" for c in body)):
            raise ValueError("커밋 본문은 최대 1500자이고 제어 문자가 없어야 합니다.")
        if not _COMMIT_LOCK.acquire(blocking=False):
            raise RuntimeError("다른 커밋 관련 작업이 진행 중입니다.")
        try:
            root, repo = _verified(project)
            snapshot = _snapshot(root)
            if snapshot["head"].lower() != expected_head.lower():
                raise RuntimeError("Git HEAD가 preview 이후 변경되었습니다.")
            if snapshot["diff_sha256"].lower() != expected_diff_sha256.lower():
                raise RuntimeError("스테이징된 diff가 preview 이후 변경되었습니다. 다시 검토하세요.")
            # Explicitly suppress repository-local hooks that might execute programs.
            # This doesn't make a user-writable local repository an OS sandbox.
            with tempfile.TemporaryDirectory(prefix="lkh-mcp-git-hooks-") as hooks:
                args = ["-c", f"core.hooksPath={hooks}", "-c", "commit.gpgsign=false",
                        "commit", "--no-verify", "-m", subject.strip()]
                if body.strip():
                    args.extend(["-m", body.strip()])
                _git(root, *args, timeout=65)
            new_branch, new_head = _head(root)
            if new_branch != snapshot["branch"] or new_head == snapshot["head"]:
                raise RuntimeError("커밋 실행 후 HEAD/브랜치 검증에 실패했습니다.")
            return {"success": True, "project": project, "github_repo": repo,
                    "branch": new_branch, "previous_head": snapshot["head"],
                    "commit": new_head, "subject": subject.strip(),
                    "files": snapshot["paths"], "pushed": False}
        finally:
            _COMMIT_LOCK.release()
