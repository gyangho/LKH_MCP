"""Repository approval CRUD and queue revocation invariants with real SQLite."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import settings_store
import repository_store as store
import codex_bridge as bridge
import codex_recovery


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "state.sqlite3"
        for p in (patch.dict(os.environ, {"MCP_DB_PATH": str(self.path), "MCP_BOOTSTRAP_FILE": str(Path(folder.name)/"none")}, clear=True), patch("dotenv.load_dotenv", return_value=False)):
            p.start(); self.addCleanup(p.stop)
        guidance_patch = patch("engineering_skills.agent_guidance", return_value="Mocked central skill")
        guidance_patch.start(); self.addCleanup(guidance_patch.stop)
        settings_store._READY = False
        self.addCleanup(lambda: setattr(settings_store, "_READY", False))
        settings_store.initialize()
        settings_store.update("CODEX_AGENT_ENABLED", True, "admin", 1)

    def test_legacy_migration_and_delete_do_not_recreate(self):
        db = settings_store._connect()
        db.execute("INSERT INTO settings(name,value,updated_at) VALUES(?,?,?)", ("GIT_ALLOWED_REPOS", json.dumps("FIRST=owner/first;SECOND=owner/second"), "old"))
        db.close()
        rows = store.list_repositories()
        self.assertEqual(store.mapping(), {"FIRST":"owner/first", "SECOND":"owner/second"})
        store.delete(rows[0]["id"], 1, "admin")
        self.assertEqual(len(store.list_repositories()), 1)
        settings_store._READY = False
        self.assertEqual(len(store.list_repositories()), 1)

    def test_crud_conflicts_and_invalid_input(self):
        item = store.create("FIRST", "owner/first", "admin")
        with self.assertRaises(store.Conflict): store.create("FIRST", "owner/duplicate", "admin")
        updated = store.update(item["id"], 1, "SECOND", "owner/second", "admin")
        self.assertEqual(updated["revision"], 2)
        self.assertEqual(bridge._allowed(), {"SECOND":"owner/second"})
        with self.assertRaises(store.Conflict): store.delete(item["id"], 1, "admin")
        for alias, repo in (("bad;alias", "owner/repo"), ("OK", "../../x"), ("OK", "owner/.."), ("OK", "https://github.com/owner/repo")):
            with self.subTest(alias=alias, repo=repo), self.assertRaises(ValueError): store.create(alias, repo, "admin")
        store.delete(item["id"], 2, "admin")
        self.assertEqual(bridge._allowed(), {})

    def test_maximum_ten(self):
        for i in range(10): store.create(f"P{i}", f"owner/repo{i}", "admin")
        with self.assertRaises(store.Conflict): store.create("EXTRA", "owner/extra", "admin")

    def test_changes_cancel_queued_and_block_running(self):
        item = store.create("FIRST", "owner/first", "admin")
        old = bridge.enqueue("FIRST", "main", "a"*40)
        result = store.update(item["id"], 1, "FIRST", "owner/second", "admin")
        self.assertEqual(result["cancelled_jobs"], 1)
        self.assertEqual(bridge.get_task(old["id"])["state"], "cancelled")
        self.assertIsNone(bridge.claim("agent", ["FIRST"])["job"])
        new = bridge.enqueue("FIRST", "main", "b"*40)
        claimed = bridge.claim("agent", ["FIRST"])
        self.assertEqual(claimed["job"]["repository"], "owner/second")
        with self.assertRaises(store.Conflict): store.delete(item["id"], 2, "admin")
        with self.assertRaises(store.Conflict): store.update(item["id"], 2, "RENAMED", "owner/third", "admin")
        self.assertEqual(store.mapping(), {"FIRST":"owner/second"})

    def test_delete_cancels_pending_fix_and_denies_new_enqueue(self):
        item = store.create("FIRST", "owner/first", "admin")
        job = bridge.enqueue("FIRST", "main", "a"*40, "fix", "Specific approved fix request")
        store.delete(item["id"], 1, "admin")
        self.assertEqual(bridge.get_task(job["id"])["state"], "cancelled")
        with self.assertRaises(ValueError): bridge.enqueue("FIRST", "main", "a"*40)

    def test_enqueue_rechecks_exact_mapping_inside_transaction(self):
        store.create("FIRST", "owner/first", "admin")
        with patch.object(bridge, "_allowed", side_effect=[{"FIRST":"owner/first"}, {"FIRST":"owner/changed"}]):
            with self.assertRaises(PermissionError): bridge.enqueue("FIRST", "main", "a"*40)
        self.assertEqual(bridge.list_tasks()["tasks"], [])

    def test_claim_rejects_a_stale_repository_snapshot(self):
        store.create("FIRST", "owner/first", "admin")
        job = bridge.enqueue("FIRST", "main", "a"*40)
        db = settings_store._connect()
        db.execute("UPDATE codex_agent_jobs SET repository='owner/obsolete' WHERE id=?", (job["id"],))
        db.close()
        self.assertIsNone(bridge.claim("agent", ["FIRST"])["job"])
        self.assertEqual(bridge.get_task(job["id"])["state"], "cancelled")

    def test_retry_uses_same_transaction_and_current_approval(self):
        item = store.create("FIRST", "owner/first", "admin")
        job = bridge.enqueue("FIRST", "main", "a"*40)
        db = settings_store._connect()
        db.execute("UPDATE codex_agent_jobs SET state='failed' WHERE id=?", (job["id"],))
        db.close()
        retried = codex_recovery.retry_failed(job["id"], "admin")
        self.assertEqual(retried["state"], "queued")
        store.delete(item["id"], 1, "admin")
        with self.assertRaises(PermissionError): codex_recovery.retry_failed(job["id"], "admin")

    def test_http_crud_auth_csrf_and_unknown_fields(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient
        from tests.test_admin_console import FakeMCP
        import admin_console
        import admin_auth
        import repository_routes
        mcp=FakeMCP(); admin_console.register_routes(mcp); repository_routes.register_repository_routes(mcp)
        app=Starlette(routes=[Route(path, handler, methods=list(methods)) for (path, methods), handler in mcp.routes.items()])
        origin="http://127.0.0.1:8001"
        headers={"Origin":origin, "X-LKH-Admin-Action":"1"}
        with patch.dict(os.environ, {"ADMIN_PUBLIC_ORIGIN":origin,"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("test-admin-password")}):
            with TestClient(app, base_url=origin) as client:
                base="/admin/api/repositories"
                self.assertEqual(client.get(base).status_code,401)
                client.post("/admin/api/login",headers=headers,json={"password":"test-admin-password"})
                self.assertEqual(client.post(base,json={"alias":"P","repository":"owner/repo"}).status_code,403)
                payload={"alias":"P", "repository":"owner/repo",
                         "agent_id":"win-test", "local_path":"C:/repositories/repo"}
                self.assertEqual(client.post(base,headers=headers,json={**payload,"extra":True}).status_code,400)
                for missing in ("agent_id", "local_path"):
                    with self.subTest(missing=missing):
                        incomplete={key:value for key,value in payload.items() if key != missing}
                        self.assertEqual(client.post(base,headers=headers,json=incomplete).status_code,400)
                self.assertEqual(client.post(base,headers=headers,json={**payload,"agent_id":"","local_path":""}).status_code,400)
                created=client.post(base,headers=headers,json=payload)
                self.assertEqual(created.status_code,201)
                self.assertEqual(created.json()["agent_id"],"win-test")
                self.assertEqual(created.json()["local_path"],"C:\\repositories\\repo")
                url=base+"/"+created.json()["id"]
                self.assertEqual(client.put(url,headers=headers,json={**payload,"alias":"Q","repository":"owner/other","revision":1}).status_code,200)
                self.assertEqual(client.request("DELETE",url,headers=headers,json={"revision":1}).status_code,409)
                self.assertEqual(client.request("DELETE",url,headers=headers,json={"revision":2}).status_code,200)
                self.assertEqual(client.get(base).json()["repositories"],[])
                client.post("/admin/api/logout",headers=headers,json={})
        admin_auth._SESSIONS.clear(); admin_auth._FAILED.clear()

if __name__ == "__main__": unittest.main()
