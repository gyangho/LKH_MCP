"""Approval-gated Codex DEBUGGING only. Never hands Git operations to Codex."""
from __future__ import annotations
import difflib
import hashlib
import hmac
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from git_tools import _verified
from git_commit_tools import _safe_path
import settings_store

_LOCK = threading.RLock()
_RUNNING = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}
_ALLOWED_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".cs", ".go", ".rs", ".html", ".css", ".scss", ".vue", ".xml"}
_TASK_ID = re.compile(r"^[0-9a-f]{32}$")
_TTL = 600


def _now():
    return datetime.now(timezone.utc).isoformat()


def _enabled():
    if settings_store.get("CODEX_DELEGATION_ENABLED") is not True:
        raise PermissionError("관리자 설정에서 Codex 디버깅을 활성화해야 합니다.")


def _job(ident):
    if not isinstance(ident, str) or not _TASK_ID.fullmatch(ident) or ident not in _TASKS:
        raise ValueError("유효하지 않은 Codex 작업 ID")
    return _TASKS[ident]


def _source(root: Path, path: str) -> bytes:
    _safe_path(root, path)
    file = root.joinpath(*path.split("/"))
    if file.suffix.lower() not in _ALLOWED_EXT or not file.is_file():
        raise ValueError("허용되지 않은 코드 파일")
    raw = file.read_bytes()
    if len(raw) > 128000 or b"\x00" in raw:
        raise ValueError("대용량 또는 바이너리 소스는 위임할 수 없습니다.")
    raw.decode("utf-8")
    return raw


def _visible(job):
    return {k: v for k, v in job.items() if k not in (
        "before", "new_files", "log_excerpt", "symptom", "approval_deadline")}


def request_debug(project: str, symptom: str, related_files: list[str],
                  log_excerpt: str = "", mode: str = "diagnose") -> dict:
    _enabled()
    if mode not in ("diagnose", "propose_fix"):
        raise ValueError("기능 개발은 위임할 수 없습니다. 오류 진단만 허용됩니다.")
    if not isinstance(symptom, str) or not 1 <= len(symptom.strip()) <= 1500:
        raise ValueError("구체적인 오류 증상이 필요합니다.")
    if not isinstance(log_excerpt, str) or len(log_excerpt) > 6000:
        raise ValueError("로그 발췌는 6000자 이하여야 합니다.")
    if not isinstance(related_files, list) or not 1 <= len(related_files) <= 12:
        raise ValueError("관련 파일은 1~12개만 지정하세요.")
    if len(set(related_files)) != len(related_files):
        raise ValueError("중복 파일은 허용되지 않습니다.")
    root, repo = _verified(project)
    before = {p: _source(root, p) for p in related_files}
    with _LOCK:
        if len(_TASKS) >= 60:
            expired = [k for k, v in _TASKS.items() if v["state"] in ("completed", "failed", "rejected", "applied")]
            if not expired:
                raise RuntimeError("작업 목록이 가득 찼습니다.")
            _TASKS.pop(expired[0])
        ident = uuid.uuid4().hex
        _TASKS[ident] = {"id": ident, "project": project, "repository": repo,
                         "files": list(related_files), "mode": mode,
                         "symptom": symptom.strip(), "log_excerpt": log_excerpt,
                         "before": before, "new_files": {}, "state": "pending",
                         "created_at": _now(), "approved_by": "",
                         "approval_deadline": 0., "report": "", "patch": "", "error": ""}
    return {"id": ident, "state": "pending", "approval_url": "/admin/codex",
            "files": related_files, "note": "관리자 페이지에서 사용자가 직접 승인해야 합니다."}


def list_tasks() -> dict:
    with _LOCK:
        return {"tasks": [_visible(x) for x in list(_TASKS.values())[-30:][::-1]]}


def get_task(ident: str) -> dict:
    with _LOCK:
        return _visible(_job(ident))


def decide(ident: str, action: str, actor: str) -> dict:
    if not actor or "@" not in actor:
        raise PermissionError("관리자 이메일 검증이 필요합니다.")
    with _LOCK:
        item = _job(ident)
        if action == "approve_run" and item["state"] == "pending":
            item["state"] = "approved"
        elif action == "reject" and item["state"] == "pending":
            item["state"] = "rejected"
        elif action == "approve_apply" and item["state"] == "completed" and item["new_files"]:
            item["state"] = "apply_approved"
        else:
            raise ValueError("이 상태에서 승인할 수 없습니다.")
        item["approved_by"] = actor
        item["approval_deadline"] = time.monotonic() + _TTL if action != "reject" else 0
        return {"id": ident, "state": item["state"], "approved_by": actor}


def _worker_token() -> str:
    file = Path("/run/secrets/codex_worker_token")
    if not file.is_file():
        raise RuntimeError("Codex worker token secret이 없습니다.")
    token = file.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("Codex worker token 길이는 최소 32자입니다.")
    return token


def _call_worker(job, before: dict[str, bytes]):
    payload = {
        "mode": job["mode"], "symptom": job["symptom"], "log_excerpt": job["log_excerpt"],
        "files": {p: raw.decode("utf-8") for p, raw in before.items()}
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > 1_500_000:
        raise ValueError("Codex 작업 요청이 너무 큽니다.")
    req = urllib.request.Request(
        "http://codex-worker:8765/execute", body,
        headers={"Content-Type": "application/json", "X-Worker-Token": _worker_token()},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=210) as response:
        data = json.loads(response.read(1_500_000).decode("utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise RuntimeError("Codex worker의 응답 형식이 잘못되었습니다.")
    if set(data["files"]) != set(before):
        raise RuntimeError("Codex가 허용되지 않은 파일을 생성·삭제했습니다.")
    changed = {}
    for path, original in before.items():
        next_text = data["files"][path]
        if not isinstance(next_text, str) or len(next_text.encode("utf-8")) > 128000:
            raise RuntimeError("Codex 결과 파일이 잘못되었습니다.")
        new = next_text.encode("utf-8")
        if job["mode"] == "diagnose" and new != original:
            raise RuntimeError("읽기 전용 분석이 파일을 변경했습니다.")
        if new != original:
            changed[path] = new
    patch = "".join(
        "".join(difflib.unified_diff(before[p].decode().splitlines(True),
                                    changed[p].decode().splitlines(True),
                                    fromfile="a/" + p, tofile="b/" + p))
        for p in changed)
    if len(patch.encode()) > 48000:
        raise RuntimeError("패치 용량 48KB 제한 초과")
    return str(data.get("report", ""))[:16000], patch, changed


def _perform(ident: str) -> None:
    try:
        with _LOCK:
            item = _job(ident)
        root, _ = _verified(item["project"])
        before = {p: _source(root, p) for p in item["files"]}
        if {p: hashlib.sha256(b).hexdigest() for p, b in before.items()} != {
            p: hashlib.sha256(b).hexdigest() for p, b in item["before"].items()}:
            raise RuntimeError("요청 이후 원본 파일이 변경되었습니다.")
        report, patch, changed = _call_worker(item, before)
        with _LOCK:
            item.update(state="completed", report=report, patch=patch, new_files=changed,
                        finished_at=_now())
    except BaseException as exc:
        with _LOCK:
            _TASKS[ident].update(state="failed", error=type(exc).__name__ + ": " + str(exc)[:220],
                                 finished_at=_now())
    finally:
        _RUNNING.release()


def run_approved(ident: str) -> dict:
    _enabled()
    with _LOCK:
        item = _job(ident)
        if item["state"] != "approved" or time.monotonic() > item["approval_deadline"]:
            raise PermissionError("유효한 관리자 실행 승인이 필요합니다.")
        # Keep the quota across restarts in the SQLite database.
        conn = settings_store._connect()
        acquired = False
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS codex_runs (at INTEGER NOT NULL)")
            conn.execute("BEGIN IMMEDIATE")
            count = conn.execute("SELECT COUNT(*) FROM codex_runs WHERE at >= ?", (int(time.time()) - 86400,)).fetchone()[0]
            if count >= settings_store.get("CODEX_MAX_RUNS_PER_DAY"):
                conn.execute("ROLLBACK")
                raise RuntimeError("일일 Codex 호출 제한에 도달했습니다.")
            if not _RUNNING.acquire(blocking=False):
                conn.execute("ROLLBACK")
                raise RuntimeError("Codex 작업이 이미 실행 중입니다.")
            acquired = True
            conn.execute("INSERT INTO codex_runs(at) VALUES(?)", (int(time.time()),))
            conn.execute("COMMIT")
        except BaseException:
            if acquired:
                _RUNNING.release()
            raise
        finally:
            conn.close()
        item["state"] = "running"
        item["approval_deadline"] = 0
        item["started_at"] = _now()
        threading.Thread(target=_perform, args=(ident,), name="Codex-debug-" + ident[:8], daemon=True).start()
    return {"id": ident, "state": "running", "note": "Codex 디버깅 결과는 codex_get_task에서 조회하세요."}


def apply_approved(ident: str) -> dict:
    _enabled()
    with _LOCK:
        item = _job(ident)
        if item["state"] != "apply_approved" or time.monotonic() > item["approval_deadline"]:
            raise PermissionError("패치 적용에 대한 별도 관리자 승인이 필요합니다.")
        root, _ = _verified(item["project"])
        for path, raw in item["before"].items():
            if _source(root, path) != raw:
                raise RuntimeError("파일이 수정되어 적용을 거부했습니다.")
        for path, raw in item["new_files"].items():
            _safe_path(root, path)
            root.joinpath(*path.split("/")).write_bytes(raw)
        item["state"] = "applied"
        item["approval_deadline"] = 0
        return {"id": ident, "state": "applied", "files": list(item["new_files"]),
                "committed": False, "pushed": False,
                "next_step": "ChatGPT가 diff 검토 후 별도 Git 승인 절차로 커밋·push합니다."}


def register_codex_tools(mcp: Any):
    @mcp.tool()
    def codex_request_debug(project: str, symptom: str, related_files: list[str],
                            log_excerpt: str = "", mode: str = "diagnose") -> dict:
        """Request bug diagnosis/minimal fix ONLY; approval required, cannot delegate feature work."""
        return request_debug(project, symptom, related_files, log_excerpt, mode)

    @mcp.tool()
    def codex_list_tasks() -> dict:
        """List statuses of debugging tasks without launching Codex."""
        return list_tasks()

    @mcp.tool()
    def codex_get_task(task_id: str) -> dict:
        """Read diagnosis, proposed diff and evidence; never commits or pushes."""
        return get_task(task_id)

    @mcp.tool()
    def codex_run_approved(task_id: str) -> dict:
        """Start only a fresh, user-approved debug task in isolated Docker worker."""
        return run_approved(task_id)

    @mcp.tool()
    def codex_apply_approved_patch(task_id: str) -> dict:
        """Apply only a separately approved patch to unchanged files, without Git operations."""
        return apply_approved(task_id)
