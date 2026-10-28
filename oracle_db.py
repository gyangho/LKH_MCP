"""Minimal Oracle connection and bounded read-only queries for MCP.

This module intentionally exposes no arbitrary SQL execution function.
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).with_name('.env'))

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,29}$")
_oracledb = None
_client_initialized = False
_client_lock = threading.Lock()


def validate_identifier(name: str) -> str:
    """Allow only ordinary, unquoted Oracle identifiers (11g-compatible length)."""
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise ValueError("Only simple Oracle identifiers (letters, digits, _, $, #; max 30 chars) are allowed")
    return name.upper()


def validate_table_reference(name: str) -> str:
    """Validate TABLE or OWNER.TABLE, without SQL expressions or quoting."""
    if not isinstance(name, str):
        raise ValueError("Table must be a string")
    parts = name.split(".")
    if len(parts) not in (1, 2):
        raise ValueError("Use TABLE or OWNER.TABLE")
    return ".".join(validate_identifier(part) for part in parts)


def get_allowed_tables() -> set[str]:
    raw = os.getenv("ORACLE_ALLOWED_TABLES", "")
    return {validate_table_reference(item.strip()) for item in raw.split(",") if item.strip()}


def _driver():
    global _oracledb, _client_initialized
    # v2 MCP runs synchronous handlers on worker threads; initialize exactly once.
    with _client_lock:
        if _oracledb is None:
            import oracledb
            _oracledb = oracledb
        if not _client_initialized:
            client_dir = os.getenv("ORACLE_CLIENT_LIB_DIR", "").strip()
            if client_dir:
                _oracledb.init_oracle_client(lib_dir=client_dir)
            _client_initialized = True
        return _oracledb


def _get_dsn(driver) -> str:
    custom_dsn = os.getenv("ORACLE_DSN", "").strip()
    if custom_dsn:
        return custom_dsn
    host = os.getenv("ORACLE_HOST", "127.0.0.1").strip()
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE", "").strip()
    sid = os.getenv("ORACLE_SID", "").strip()
    if bool(service) == bool(sid):
        raise ValueError("Configure exactly one of ORACLE_SERVICE or ORACLE_SID (or use ORACLE_DSN)")
    if sid:
        return driver.makedsn(host, port, sid=sid)
    return driver.makedsn(host, port, service_name=service)


@contextmanager
def connection() -> Iterator:
    driver = _driver()
    user = os.getenv("ORACLE_USER", "").strip()
    password = os.getenv("ORACLE_PASSWORD", "")
    if not user or not password or password == "CHANGE_ME":
        raise ValueError("Set ORACLE_USER and a real ORACLE_PASSWORD in .env")
    dsn = _get_dsn(driver)
    with driver.connect(user=user, password=password, dsn=dsn) as conn:
        # Oracle client call timeout, milliseconds. Protect against stalled queries.
        conn.call_timeout = 8000
        yield conn


def _clean_cell(value):
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "<binary omitted>"
    if hasattr(value, "read"):
        return "<LOB omitted>"
    text = str(value)
    return text if len(text) <= 512 else text[:512] + "…[truncated]"


def test_select() -> dict:
    """Fixed safe SELECT from Oracle DUAL; proves driver/DB path is functioning."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 'MCP_OK' AS STATUS FROM DUAL")
            row = cur.fetchone()
            cur.execute("SELECT USER FROM DUAL")
            db_user = cur.fetchone()[0]
            return {"status": row[0], "database_user": db_user, "database_version": conn.version,
                    "mode": "Thin" if conn.thin else "Thick"}


def list_tables(limit: int = 30) -> dict:
    """List only explicit allowlist entries accessible by the configured user."""
    limit = max(1, min(int(limit), 100))
    allowed = sorted(get_allowed_tables())
    if not allowed:
        return {"tables": [], "count": 0, "notice": "Set ORACLE_ALLOWED_TABLES to enable table discovery"}
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT USER FROM DUAL")
            username = cur.fetchone()[0]
            visible = []
            for name in allowed[:100]:
                owner, table = name.split(".") if "." in name else (username, name)
                cur.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER=:owner AND TABLE_NAME=:name",
                            owner=owner, name=table)
                if cur.fetchone()[0] == 1:
                    visible.append(f"{owner}.{table}")
                if len(visible) >= limit:
                    break
    return {"tables": visible, "count": len(visible), "max_rows": limit}


def preview_table(table_name: str, limit: int = 5) -> dict:
    """Preview only an explicit allowlist table accessible to the DB account."""
    ref = validate_table_reference(table_name)
    allowed = get_allowed_tables()
    if ref not in allowed:
        raise PermissionError("Table is not allowlisted in ORACLE_ALLOWED_TABLES")
    limit = max(1, min(int(limit), 20))
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT USER FROM DUAL")
            username = cur.fetchone()[0]
            owner, table = ref.split(".") if "." in ref else (username, ref)
            cur.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER=:owner AND TABLE_NAME=:name",
                        owner=owner, name=table)
            if cur.fetchone()[0] != 1:
                raise PermissionError("Table is not accessible to the DB user")
            # Both identifiers were validated before interpolation.
            cur.execute(f'SELECT * FROM "{owner}"."{table}" WHERE ROWNUM <= :max_rows', max_rows=limit)
            columns = [col[0] for col in cur.description]
            rows = [[_clean_cell(v) for v in record] for record in cur.fetchall()]
            return {"table": f"{owner}.{table}", "columns": columns, "rows": rows,
                    "row_count": len(rows), "max_rows": limit}
