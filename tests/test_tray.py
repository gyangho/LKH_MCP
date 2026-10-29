"""Tests for safe tray routing without Windows GUI dependencies."""
import os
import unittest
from unittest.mock import patch

import tray


class TestTray(unittest.TestCase):
    def test_dashboard_origin(self):
        with patch.dict(os.environ, {"ADMIN_PUBLIC_ORIGIN": "https://mcp.gyangho.com"}):
            self.assertEqual(tray._dashboard_url(), "https://mcp.gyangho.com/admin")

    def test_rejects_insecure_dashboard_origin(self):
        for address in ("http://mcp.gyangho.com", "https://other.test/admin",
                        "https://name:password@mcp.gyangho.com"):
            with self.subTest(address=address):
                with patch.dict(os.environ, {"ADMIN_PUBLIC_ORIGIN": address}):
                    with self.assertRaises(ValueError):
                        tray._dashboard_url()

    def test_health_failure_is_false(self):
        with patch("tray.urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertFalse(tray._is_healthy())


if __name__ == "__main__":
    unittest.main()
