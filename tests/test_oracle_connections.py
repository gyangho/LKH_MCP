"""Profile isolation, migration, revision safety and secret non-disclosure."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import settings_store
import oracle_connections as store
import oracle_db


def profile(**changes):
    return {"name": "개발 DB", "host": "127.0.0.1", "port": 1521, "service": "DEV",
            "sid": "", "dsn": "", "username": "reader", "allowed_tables": "APP.SAFE", "enabled": True, **changes}


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "db.sqlite3"
        for context in (
            patch.dict(os.environ, {"MCP_DB_PATH": str(self.path), "MCP_BOOTSTRAP_FILE": str(Path(tmp.name) / "missing.json")}, clear=True),
            patch("dotenv.load_dotenv", return_value=False),
            patch.object(store, "protect", side_effect=lambda p: b"encrypted-test-blob"),
            patch.object(store, "unprotect", return_value="private-db-password"),
        ):
            context.start(); self.addCleanup(context.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))

    def test_name_resolution_requires_explicit_unique_enabled_connection(self):
        item = store.create(profile(name="itam-prod"), "test", "admin")
        self.assertEqual(store.resolve_connection(name="itam-prod"), item["id"])
        self.assertEqual(store.resolve_connection(connection_id=item["id"]), item["id"])
        with self.assertRaises(ValueError):
            store.resolve_connection()
        with self.assertRaises(ValueError):
            store.resolve_connection(name="itam-prod", connection_id=item["id"])
        store.create(profile(name="itam-prod"), "test", "admin")
        with self.assertRaises(ValueError):
            store.resolve_connection(name="itam-prod")
        with self.assertRaises(store.NotFound):
            store.resolve_connection(name="unknown")

    def test_crud_password_preservation_and_no_plaintext(self):
        item = store.create(profile(), "private-db-password", "admin")
        self.assertNotIn("password", item)
        self.assertNotIn("private-db-password", json.dumps(store.list_connections()))
        self.assertNotIn(b"private-db-password", self.path.read_bytes())
        saved = store.update(item["id"], 1, profile(name="新 DB"), "", "admin")
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(store.credentials(item["id"])["password"], "private-db-password")
        with self.assertRaises(store.Conflict):
            store.update(item["id"], 1, profile(), "replacement", "admin")
        with self.assertRaises(store.Conflict):
            store.delete(item["id"], 1, "admin")
        store.delete(item["id"], 2, "admin")
        self.assertEqual(store.list_connections(), [])
        with self.assertRaises(store.NotFound):
            store.credentials(item["id"])

    def test_disabled_and_mcp_metadata_minimized(self):
        item = store.create(profile(), "secret", "admin")
        self.assertEqual(store.list_connections(mcp=True), [{"id": item["id"], "name": "개발 DB"}])
        store.update(item["id"], 1, profile(enabled=False), "", "admin")
        self.assertEqual(store.list_connections(mcp=True), [])
        with self.assertRaises(PermissionError):
            store.credentials(item["id"])
        self.assertFalse(store.credentials(item["id"], allow_disabled=True)["enabled"])

    def test_legacy_import_once_even_after_deletion(self):
        settings_store.initialize()
        db = settings_store._connect()
        for key, val in {"ORACLE_USER": "old_reader", "ORACLE_SERVICE": "OLD", "ORACLE_ALLOWED_TABLES": "APP.OLD"}.items():
            db.execute("INSERT INTO settings(name,value,updated_at) VALUES(?,?,?)", (key, json.dumps(val), "old"))
        db.close()
        with patch.dict(os.environ, {"ORACLE_PASSWORD": "legacy-secret"}):
            rows = store.list_connections()
            self.assertEqual(rows[0]["id"], "legacy")
            self.assertEqual(rows[0]["username"], "old_reader")
            store.delete("legacy", 1, "admin")
            self.assertEqual(store.list_connections(), [])
        self.assertNotIn(b"legacy-secret", self.path.read_bytes())

    def test_crypto_failure_does_not_store_profile(self):
        with patch.object(store, "protect", side_effect=RuntimeError("unavailable")):
            with self.assertRaises(RuntimeError):
                store.create(profile(), "secret", "admin")
        self.assertEqual(store.list_connections(), [])

    def test_profile_validation(self):
        for changes in ({"port": True}, {"port": 70000}, {"enabled": "true"}, {"service": "DEV", "sid": "SID"},
                        {"allowed_tables": "APP.SAFE;DROP"}, {"host": "x\nother"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                store.create(profile(**changes), "secret", "admin")

    def test_connection_allowlists_are_isolated(self):
        first = store.create(profile(allowed_tables="APP.FIRST"), "first", "admin")
        second = store.create(profile(name="Second", allowed_tables="APP.SECOND"), "second", "admin")
        with patch.object(oracle_db, "connection") as connection:
            with self.assertRaises(PermissionError):
                oracle_db.preview_table(first["id"], "APP.SECOND")
            with self.assertRaises(PermissionError):
                oracle_db.preview_table(second["id"], "APP.FIRST")
            connection.assert_not_called()

    def test_unqualified_allowlist_accepts_own_schema_but_not_another(self):
        p = {"allowed_tables": "SAFE"}
        conn = MagicMock()
        cursor = conn.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("READER",), (1,)]
        cursor.description = [("ID",)]
        cursor.fetchall.return_value = [(1,)]
        with patch.object(oracle_db, "_profile", return_value=p), patch.object(oracle_db, "connection") as opened:
            opened.return_value.__enter__.return_value = conn
            self.assertEqual(oracle_db.preview_table("id", "READER.SAFE")["rows"], [[1]])
            cursor.fetchone.side_effect = [("READER",)]
            with self.assertRaises(PermissionError):
                oracle_db.preview_table("id", "OTHER.SAFE")

    def test_dsn_and_driver_credential_selection(self):
        p = {**profile(), "password": "secret"}
        driver = MagicMock()
        driver.makedsn.return_value = "selected-dsn"
        with patch.object(oracle_db, "_driver", return_value=driver):
            with oracle_db.connection(p): pass
        driver.connect.assert_called_once_with(user="reader", password="secret", dsn="selected-dsn", tcp_connect_timeout=8, retry_count=0)
        driver.connect.side_effect = RuntimeError("password=secret")
        with patch.object(oracle_db, "_driver", return_value=driver):
            with self.assertRaises(oracle_db.OracleUnavailable) as err:
                with oracle_db.connection(p): pass
        self.assertNotIn("secret", str(err.exception))


    def test_http_crud_with_real_session_and_csrf(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        from tests.test_admin_console import FakeMCP
        import admin_console
        import admin_auth
        import oracle_routes
        mcp = FakeMCP()
        admin_console.register_routes(mcp)
        oracle_routes.register_oracle_routes(mcp)
        app = Starlette(routes=[Route(path, handler, methods=list(methods)) for (path, methods), handler in mcp.routes.items()])
        origin = "http://127.0.0.1:8001"
        headers = {"Origin": origin, "X-LKH-Admin-Action": "1"}
        with patch.dict(os.environ, {"ADMIN_PUBLIC_ORIGIN": origin, "ADMIN_PASSWORD_HASH": admin_auth.make_password_hash("test-admin-password")}):
            with TestClient(app, base_url=origin) as client:
                base = "/admin/api/oracle/connections"
                self.assertEqual(client.get(base).status_code, 401)
                self.assertEqual(client.post("/admin/api/login", headers=headers, json={"password": "test-admin-password"}).status_code, 200)
                self.assertEqual(client.post(base, json={**profile(), "password": "secret"}).status_code, 403)
                created = client.post(base, headers=headers, json={**profile(), "password": "secret"})
                self.assertEqual(created.status_code, 201)
                item = created.json()
                self.assertNotIn("password", item)
                ident = item["id"]
                url = f"{base}/{ident}"
                changed = client.put(url, headers=headers, json={**profile(enabled=False), "password": "", "revision": 1})
                self.assertEqual(changed.status_code, 200)
                self.assertEqual(client.put(url, headers=headers, json={**profile(), "password": "", "revision": 1}).status_code, 409)
                self.assertEqual(client.get(base).json()["connections"][0]["revision"], 2)
                self.assertEqual(client.request("DELETE", url, headers=headers, json={"revision": 2}).status_code, 200)
                self.assertEqual(client.get(base).json()["connections"], [])
                client.post("/admin/api/logout", headers=headers, json={})
        admin_auth._SESSIONS.clear()
        admin_auth._FAILED.clear()


@unittest.skipUnless(os.name == "nt", "Windows DPAPI only")
class WindowsPasswordTests(unittest.TestCase):
    def test_actual_dpapi_roundtrip(self):
        try:
            import win32crypt
        except ImportError:
            self.skipTest("pywin32 not installed")
        password = "Synthetic-roundtrip-only-秘密99!"
        blob = store.protect(password)
        self.assertNotIn(password.encode("utf-8"), blob)
        self.assertEqual(store.unprotect(blob), password)


if __name__ == "__main__": unittest.main()
