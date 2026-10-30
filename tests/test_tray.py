"""Tests for private admin tray links without Windows GUI."""
import os
import unittest
from unittest.mock import patch
import tray

class TestTray(unittest.TestCase):
    def test_private_origin(self):
        with patch.dict(os.environ,{"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            self.assertEqual(tray._dashboard_url(),"http://192.0.1.22:8001/admin")
    def test_rejects_untrusted_origin(self):
        for address in ("http://mcp.gyangho.com:8001","https://other.test/admin","http://name:password@192.0.1.22:8001","http://192.0.1.22"):
            with self.subTest(address=address),patch.dict(os.environ,{"ADMIN_PUBLIC_ORIGIN":address}):
                with self.assertRaises(ValueError): tray._dashboard_url()
    def test_health_failure(self):
        with patch("tray.urllib.request.urlopen",side_effect=OSError("offline")):
            self.assertFalse(tray._is_healthy())
if __name__=="__main__":unittest.main()
