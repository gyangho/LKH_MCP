"""Tests for I1 native preview config. No Windows services or listener used."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_runtime


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "native"
        self.env = {}

    def test_isolated_state_uses_independent_database(self):
        root = native_runtime.prepare_native_environment(self.env, root=self.root)
        self.assertEqual(root, self.root)
        self.assertEqual(self.env["MCP_HOST"], "127.0.0.1")
        self.assertEqual(self.env["MCP_PORT"], "18080")
        self.assertEqual(self.env["MCP_DB_PATH"], str(self.root / "data" / "mcp.sqlite3"))
        self.assertTrue((self.root / "logs").is_dir())
        self.assertTrue((self.root / "data").is_dir())
        self.assertNotIn("MCP_BOOTSTRAP_FILE", self.env)

    def test_existing_bootstrap_discovered_but_not_copied(self):
        config = self.root / "config"
        config.mkdir(parents=True)
        secret = config / "bootstrap.json"
        secret.write_text('{"ADMIN_LOGIN_USER":"ci"}', encoding="utf-8")
        native_runtime.prepare_native_environment(self.env, root=self.root)
        self.assertEqual(self.env["MCP_BOOTSTRAP_FILE"], str(secret))
        self.assertEqual(secret.read_text(encoding="utf-8"), '{"ADMIN_LOGIN_USER":"ci"}')

    def test_explicit_absolute_paths_preserved(self):
        self.env = {
            "MCP_DB_PATH": str(self.root / "separate.sqlite3"),
            "MCP_BOOTSTRAP_FILE": str(self.root / "secret.json"),
            "MCP_PORT": "19000",
        }
        native_runtime.prepare_native_environment(self.env, root=self.root)
        self.assertEqual(self.env["MCP_DB_PATH"], str(self.root / "separate.sqlite3"))
        self.assertEqual(self.env["MCP_PORT"], "19000")

    def test_rejects_nonloopback_before_any_directory_created(self):
        for host in ("0.0.0.0", "192.0.1.22", "[::]", "example.com"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    native_runtime.prepare_native_environment({"MCP_HOST": host}, root=self.root)
                self.assertFalse(self.root.exists())

    def test_rejects_relative_state_or_database_or_secret(self):
        with self.assertRaises(ValueError):
            native_runtime.prepare_native_environment({}, root=Path("relative"))
        for key, val in (("MCP_DB_PATH", "db.sqlite3"), ("MCP_BOOTSTRAP_FILE", "secret.json")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                native_runtime.prepare_native_environment({key: val}, root=self.root)

    def test_port_validation(self):
        for p in ("0", "65536", "-1", "not-a-port", "8000;evil"):
            with self.subTest(port=p), self.assertRaises(ValueError):
                native_runtime.prepare_native_environment({"MCP_PORT": p}, root=self.root)

    def test_asset_checks_are_explicit(self):
        self.assertEqual(native_runtime.required_assets(self.root),
                         {"admin_html": False, "uiux_search": False})
        html = self.root / "web" / "dist" / "index.html"
        uiux = self.root / "vendor" / "ui-ux-pro-max-skill" / "src" / "ui-ux-pro-max" / "scripts" / "search.py"
        html.parent.mkdir(parents=True)
        uiux.parent.mkdir(parents=True)
        html.write_text("ok", encoding="utf-8")
        uiux.write_text("ok", encoding="utf-8")
        self.assertEqual(native_runtime.required_assets(self.root),
                         {"admin_html": True, "uiux_search": True})


if __name__ == "__main__":
    unittest.main()
