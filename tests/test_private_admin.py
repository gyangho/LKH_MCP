"""Authentication helper regression tests."""
import os
import unittest
from unittest.mock import patch
from starlette.requests import Request
from starlette.responses import JSONResponse
import admin_auth

def request(headers=None):
    scope={"type":"http","method":"POST","path":"/admin/api/config","headers":[(k.encode(),v.encode()) for k,v in (headers or {}).items()],"query_string":b""}
    return Request(scope)

class AuthTests(unittest.TestCase):
    def setUp(self):
        admin_auth._SESSIONS.clear();admin_auth._FAILED.clear()
    def test_password_hash_roundtrip(self):
        hashed=admin_auth.make_password_hash("some-very-long-password")
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":hashed,"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            self.assertTrue(admin_auth.check_password("some-very-long-password"))
            self.assertFalse(admin_auth.check_password("wrong"))
    def test_rate_limit(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("some-very-long-password"),"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            for _ in range(5):admin_auth.record_failure()
            self.assertFalse(admin_auth.login_allowed())
    def test_wrong_origin_and_host(self):
        with patch.dict(os.environ,{"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            self.assertFalse(admin_auth.valid_csrf(request({"host":"wrong","origin":"http://192.0.1.22:8001","x-lkh-admin-action":"1","content-type":"application/json"})))
            self.assertTrue(admin_auth.valid_csrf(request({"host":"192.0.1.22:8001","origin":"http://192.0.1.22:8001","x-lkh-admin-action":"1","content-type":"application/json"})))
    def test_session_is_not_bearer_header(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("some-very-long-password"),"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            response=JSONResponse({"ok":True});admin_auth.issue_session(response)
            self.assertEqual(response.status_code,200)
            with self.assertRaises(admin_auth.AdminUnauthorized):
                admin_auth.verify_admin_session(request({"cf-access-jwt-assertion":"fake"}))
if __name__=="__main__":unittest.main()
