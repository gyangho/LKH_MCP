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


def get_allowed_tables(raw: str) -> set[str]:
    """Return explicit allowlist, or {"*"} for all visible Oracle tables.

    Wildcard is intentionally opt-in and must appear alone. Database permissions
    are still enforced by Oracle; never expose this mode without MCP auth.
    """
    raw = raw.strip()
    if raw == "*":
        return {"*"}
    if "*" in raw:
        raise ValueError("ORACLE_ALLOWED_TABLES: '*' must be used alone")
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
                path = Path(client_dir).expanduser()
                if not path.is_absolute():
                    path = Path(__file__).resolve().parent.parent / path
                _oracledb.init_oracle_client(lib_dir=str(path.resolve()))
            _client_initialized = True
        return _oracledb


def _get_dsn(driver, profile) -> str:
    custom_dsn = profile["dsn"]
    if custom_dsn:
        return custom_dsn
    host, port = profile["host"], profile["port"]
    service, sid = profile["service"], profile["sid"]
    if bool(service) == bool(sid):
        raise ValueError("Configure exactly one of ORACLE_SERVICE or ORACLE_SID (or use ORACLE_DSN)")
    if sid:
        return driver.makedsn(host, port, sid=sid)
    return driver.makedsn(host, port, service_name=service)


class OracleUnavailable(RuntimeError):
    pass


@contextmanager
def connection(profile) -> Iterator:
    try:
        driver = _driver()
        with driver.connect(user=profile["username"], password=profile["password"],
                            dsn=_get_dsn(driver, profile), tcp_connect_timeout=8, retry_count=0) as conn:
            conn.call_timeout = 8000
            yield conn
    except Exception:
        # Never return driver errors containing DSNs, accounts or credentials.
        raise OracleUnavailable("Oracle connection or query failed") from None


def _profile(connection_id, *, allow_disabled=False):
    from oracle_connections import credentials
    return credentials(connection_id, allow_disabled=allow_disabled)


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


def test_select(connection_id: str, *, allow_disabled=False) -> dict:
    """Fixed safe SELECT from Oracle DUAL; proves driver/DB path is functioning."""
    profile = _profile(connection_id, allow_disabled=allow_disabled)
    with connection(profile) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 'MCP_OK' AS STATUS FROM DUAL")
            row = cur.fetchone()
            cur.execute("SELECT USER FROM DUAL")
            db_user = cur.fetchone()[0]
            return {"status": row[0], "database_user": db_user, "database_version": conn.version,
                    "mode": "Thin" if conn.thin else "Thick"}


def list_tables(connection_id: str, limit: int = 30) -> dict:
    """List explicitly allowlisted tables or all ALL_TABLES in '*' mode."""
    limit = max(1, min(int(limit), 100))
    profile = _profile(connection_id)
    allowed = sorted(get_allowed_tables(profile["allowed_tables"]))
    if not allowed:
        return {"tables": [], "count": 0, "notice": "Configure this connection’s allowed tables to enable discovery"}
    with connection(profile) as conn:
        with conn.cursor() as cur:
            if allowed == ["*"]:
                # 11g-compatible pagination; only fetch up to the requested cap.
                cur.execute(
                    "SELECT OWNER, TABLE_NAME FROM ("
                    "SELECT OWNER, TABLE_NAME FROM ALL_TABLES ORDER BY OWNER, TABLE_NAME"
                    ") WHERE ROWNUM <= :lim", lim=limit
                )
                visible = [f"{owner}.{table}" for owner, table in cur.fetchall()]
            else:
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
    return {"tables": visible, "count": len(visible), "max_rows": limit, "all_visible_mode": allowed == ["*"]}

def preview_table(connection_id: str, table_name: str, limit: int = 5) -> dict:
    """Preview only an explicit allowlist table accessible to the DB account."""
    ref = validate_table_reference(table_name)
    profile = _profile(connection_id)
    allowed = get_allowed_tables(profile["allowed_tables"])
    if "*" not in allowed and ref not in allowed and ref.split(".")[-1] not in allowed:
        raise PermissionError("Table is not allowlisted for this connection")
    limit = max(1, min(int(limit), 20))
    with connection(profile) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT USER FROM DUAL")
            username = cur.fetchone()[0]
            owner, table = ref.split(".") if "." in ref else (username, ref)
            if "*" not in allowed and ref not in allowed and not (owner == username and table in allowed):
                raise PermissionError("Table is not allowlisted for this connection")
            cur.execute("SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER=:owner AND TABLE_NAME=:name",
                        owner=owner, name=table)
            if cur.fetchone()[0] != 1:
                raise PermissionError("Table is not accessible to the DB user")
            owner, table = validate_identifier(owner), validate_identifier(table)
            # Both identifiers were validated before interpolation.
            cur.execute(f'SELECT * FROM "{owner}"."{table}" WHERE ROWNUM <= :max_rows', max_rows=limit)
            columns = [col[0] for col in cur.description]
            rows = [[_clean_cell(v) for v in record] for record in cur.fetchall()]
            return {"table": f"{owner}.{table}", "columns": columns, "rows": rows,
                    "row_count": len(rows), "max_rows": limit}
