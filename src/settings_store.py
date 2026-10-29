"""SQLite configuration store for LKH MCP. Secrets never enter the database."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.RLock()
_READY = False

# key: (category, label, type, default, description)
FIELDS = {
    "GIT_ALLOW_COMMIT": ("git", "로컬 커밋", "bool", False, "Git 스테이징과 AI 리뷰 커밋 허용"),
    "GIT_ALLOW_PUSH": ("git", "GitHub Push", "bool", False, "확인된 HEAD의 fast-forward push 허용"),
    "GIT_ALLOWED_REPOS": ("git", "허용 Git 저장소", "text", "", "PROJECT=owner/repo;..."),
    "GIT_EXECUTABLE": ("git", "Git 실행 파일", "text", "", "비우면 PATH에서 검색"),
    "GRAPHIFY_ALLOW_UPDATE": ("graphify", "그래프 갱신", "bool", False, "코드 그래프 변경 허용"),
    "GRAPHIFY_PROJECTS": ("projects", "프로젝트 경로", "text", "", "PROJECT=/projects/name;..."),
    "GRAPHIFY_EXECUTABLE": ("graphify", "Graphify 실행 파일", "text", "", "비우면 PATH에서 검색"),
    "CODEX_DELEGATION_ENABLED": ("codex", "Codex 디버깅 위임", "bool", False, "관리자 승인 후에만 실행"),
    "CODEX_MAX_RUNS_PER_DAY": ("codex", "일일 Codex 실행 제한", "int", 2, "1~10회"),
    "CODEX_EXECUTABLE": ("codex", "Codex 실행 파일", "text", "", "실행 가능한 절대 경로 (컨테이너 내부 경로)"),
    "ORACLE_HOST": ("oracle", "Oracle 주소", "text", "127.0.0.1", "Docker라면 host.docker.internal 또는 DB 주소"),
    "ORACLE_PORT": ("oracle", "Oracle 포트", "int", 1521, "1~65535"),
    "ORACLE_SERVICE": ("oracle", "서비스 이름", "text", "", "SERVICE 또는 SID 중 한 개"),
    "ORACLE_SID": ("oracle", "SID", "text", "", "SERVICE 대신 사용할 경우"),
    "ORACLE_DSN": ("oracle", "DSN", "text", "", "설정된 경우 HOST/PORT 대신 사용"),
    "ORACLE_USER": ("oracle", "DB 사용자", "text", "", "Oracle 읽기 전용 계정"),
    "ORACLE_ALLOWED_TABLES": ("oracle", "조회 허용 테이블", "text", "", "쉼표 구분, 명시적 허용 목록"),
    "ORACLE_CLIENT_LIB_DIR": ("oracle", "Oracle Client 디렉터리", "text", "", "Thick 모드 사용 시 컨테이너 경로"),
}
SECRETS = frozenset({"ORACLE_PASSWORD", "ADMIN_CF_TEAM", "ADMIN_CF_AUD", "ADMIN_ALLOWED_EMAILS", "ADMIN_PUBLIC_ORIGIN"})
_PATH_FIELDS = {"CODEX_EXECUTABLE", "GIT_EXECUTABLE", "GRAPHIFY_EXECUTABLE", "ORACLE_CLIENT_LIB_DIR"}
_BOOL_FIELDS = {key for key, item in FIELDS.items() if item[2] == "bool"}


def db_path() -> Path:
    return Path(os.environ.get("MCP_DB_PATH", "data/mcp.sqlite3")).expanduser().resolve()


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS settings "
                 "(name TEXT PRIMARY KEY, value TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE IF NOT EXISTS audit "
                 "(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, name TEXT NOT NULL, "
                 "old_value TEXT NOT NULL, new_value TEXT NOT NULL)")
    return conn


def _validate(key: str, value: Any) -> Any:
    if key not in FIELDS:
        raise ValueError("허용되지 않은 설정 키입니다.")
    kind = FIELDS[key][2]
    if kind == "bool" and type(value) is not bool:
        raise ValueError("boolean 설정 값이 아닙니다.")
    if kind == "int":
        if type(value) is not int:
            raise ValueError("정수 설정 값이 아닙니다.")
        lower, upper = (1, 10) if key == "CODEX_MAX_RUNS_PER_DAY" else (1, 65535)
        if not lower <= value <= upper:
            raise ValueError("설정 범위를 벗어났습니다.")
    if kind == "text":
        if not isinstance(value, str) or len(value) > 3000 or "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError("설정 텍스트 길이 또는 문자 제한 위반")
        if key in _PATH_FIELDS and value and not Path(value).is_absolute():
            raise ValueError("경로는 절대 경로여야 합니다.")
        if key in ("GRAPHIFY_PROJECTS", "GIT_ALLOWED_REPOS") and value:
            entries = value.split(";")
            if len(entries) > 10:
                raise ValueError("프로젝트는 최대 10개입니다.")
            for entry in entries:
                if "=" not in entry or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", entry.split("=", 1)[0]):
                    raise ValueError("PROJECT=경로 또는 PROJECT=owner/repo 형식이 필요합니다.")
        if key == "ORACLE_ALLOWED_TABLES" and len(value) > 2000:
            raise ValueError("테이블 허용 목록이 너무 깁니다.")
    return value


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _as_env(value: Any) -> str:
    return str(value).lower() if type(value) is bool else str(value)


def initialize() -> None:
    global _READY
    with _LOCK:
        if _READY:
            return
        # Backwards compatibility: one-time import of existing local .env settings.
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
        bootstrap = Path(os.environ.get("MCP_BOOTSTRAP_FILE", "/run/secrets/mcp_bootstrap.json"))
        if bootstrap.is_file():
            data = json.loads(bootstrap.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) - SECRETS:
                raise ValueError("bootstrap file may contain only approved secret/bootstrap keys")
            for key, value in data.items():
                if not isinstance(value, str) or len(value) > 4096:
                    raise ValueError("Invalid bootstrap value")
                os.environ[key] = value
        conn = _connect()
        try:
            for key, (_, _, _, default, _) in FIELDS.items():
                previous = os.environ.get(key)
                value = default
                if previous is not None:
                    if key in _BOOL_FIELDS:
                        value = previous.lower() == "true"
                    elif FIELDS[key][2] == "int":
                        value = int(previous)
                    else:
                        value = previous
                value = _validate(key, value)
                conn.execute("INSERT OR IGNORE INTO settings(name,value,updated_at) VALUES(?,?,?)",
                             (key, _encode(value), _timestamp()))
            _apply(conn)
            _READY = True
        finally:
            conn.close()


def _apply(conn: sqlite3.Connection) -> None:
    for name, value in conn.execute("SELECT name,value FROM settings"):
        if name in FIELDS:
            os.environ[name] = _as_env(json.loads(value))


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(key: str) -> Any:
    initialize()
    if key not in FIELDS:
        raise ValueError("Unknown setting")
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT value FROM settings WHERE name=?", (key,)).fetchone()
            return json.loads(row[0])
        finally:
            conn.close()


def items() -> list[dict]:
    initialize()
    with _LOCK:
        conn = _connect()
        try:
            values = {name: (json.loads(value), version) for name, value, version in
                      conn.execute("SELECT name,value,revision FROM settings")}
        finally:
            conn.close()
    return [{"key": key, "category": spec[0], "label": spec[1], "type": spec[2],
             "enabled": values[key][0] if spec[2] == "bool" else None,
             "value": values[key][0], "revision": values[key][1], "description": spec[4]}
            for key, spec in FIELDS.items()]


def update(key: str, value: Any, actor: str, expected_revision: int) -> dict:
    initialize()
    value = _validate(key, value)
    if not actor or len(actor) > 256 or type(expected_revision) is not int:
        raise ValueError("actor or revision invalid")
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT value,revision FROM settings WHERE name=?", (key,)).fetchone()
            if row is None:
                raise ValueError("Unknown setting")
            if row[1] != expected_revision:
                raise ValueError("설정이 다른 관리자에 의해 수정되었습니다. 새로고침하세요.")
            conn.execute("UPDATE settings SET value=?,revision=revision+1,updated_at=? WHERE name=?",
                         (_encode(value), _timestamp(), key))
            conn.execute("INSERT INTO audit(at,actor,name,old_value,new_value) VALUES(?,?,?,?,?)",
                         (_timestamp(), actor, key, row[0], _encode(value)))
            conn.execute("COMMIT")
            os.environ[key] = _as_env(value)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
    return {"key": key, "value": value, "revision": expected_revision + 1, "saved": True}


def audit_events(limit: int = 30) -> list[dict]:
    initialize()
    conn = _connect()
    try:
        rows = conn.execute("SELECT at,actor,name FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(50, limit)),))
        return [{"at": a, "actor": actor, "key": key} for a, actor, key in rows]
    finally:
        conn.close()
