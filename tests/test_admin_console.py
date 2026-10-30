"""Private-admin route authentication regression tests."""
import asyncio
import json
import os
import unittest
from unittest.mock import patch
from starlette.requests import Request
import admin_console
import admin_auth

class FakeMCP:
    def __init__(self):
        self.routes={}
    def custom_route(self, path, methods):
        def register(fn):
            self.routes[(path, tuple(methods))]=fn
            return fn
        return register

def make_request(path="/admin/api/status", method="GET", headers=None, body=b""):
    headers={"host":"192.0.1.22:8001",**(headers or {})}
    raw=[(k.lower().encode("latin1"),str(v).encode("latin1")) for k,v in headers.items()]
    scope={"type":"http","method":method,"path":path,"headers":raw,"query_string":b"","scheme":"http"}
    async def receive(): return {"type":"http.request","body":body,"more_body":False}
    return Request(scope,receive)

class AdminTests(unittest.TestCase):
    def setUp(self):
        mcp=FakeMCP();admin_console.register_routes(mcp);self.routes=mcp.routes
        admin_auth._SESSIONS.clear();admin_auth._FAILED.clear()
        self.addCleanup(admin_auth._SESSIONS.clear)
        self.addCleanup(admin_auth._FAILED.clear)
    def invoke(self,path,method="GET",headers=None,body=b""):
        return asyncio.run(self.routes[(path,(method,))](make_request(path,method,headers,body)))
    def test_health(self):
        self.assertEqual(json.loads(self.invoke("/healthz").body),{"status":"ok"})
    def test_default_fail_closed(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":"","ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            self.assertEqual(self.invoke("/admin/api/status").status_code,503)
    def test_denied_no_cookie(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("long-test-password"),"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            self.assertEqual(self.invoke("/admin/api/status").status_code,401)
    def test_csrf_rejects_bad_origin(self):
        with patch.object(admin_console,"_verify_access",return_value="admin"):
            with patch.dict(os.environ,{"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
                result=self.invoke("/admin/api/flags","POST",{"origin":"http://evil.test","content-type":"application/json","x-lkh-admin-action":"1"},b'{"key":"GIT_ALLOW_PUSH","enabled":true}')
                self.assertEqual(result.status_code,403)
    def test_csrf_accepts_matching_origin(self):
        with patch.object(admin_console,"_verify_access",return_value="admin"):
            with patch.dict(os.environ,{"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
                with patch.object(admin_console,"change_flag",return_value={"saved":True}) as save:
                    data=self.invoke("/admin/api/flags","POST",{"origin":"http://192.0.1.22:8001","content-type":"application/json","x-lkh-admin-action":"1"},b'{"key":"GIT_ALLOW_PUSH","enabled":true}')
                    self.assertEqual(data.status_code,200)
                    save.assert_called_once_with("GIT_ALLOW_PUSH",True,"admin")
    def test_invalid_login_rejected(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("long-test-password"),"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            response=self.invoke("/admin/api/login","POST",{"origin":"http://192.0.1.22:8001","content-type":"application/json","x-lkh-admin-action":"1"},b'{"password":"bad"}')
            self.assertEqual(response.status_code,401)
    def test_session_login_logout(self):
        with patch.dict(os.environ,{"ADMIN_PASSWORD_HASH":admin_auth.make_password_hash("long-test-password"),"ADMIN_PUBLIC_ORIGIN":"http://192.0.1.22:8001"}):
            h={"origin":"http://192.0.1.22:8001","content-type":"application/json","x-lkh-admin-action":"1"}
            login=self.invoke("/admin/api/login","POST",h,b'{"password":"long-test-password"}')
            self.assertEqual(login.status_code,200)
            cookie=login.headers["set-cookie"].split(";",1)[0]
            self.assertIn("httponly",login.headers["set-cookie"].lower())
            with patch.object(admin_console,"telemetry",return_value={"version":"test"}):
                res=self.invoke("/admin/api/status","GET",{"cookie":cookie})
                self.assertEqual(res.status_code,200)
            out=self.invoke("/admin/api/logout","POST",{**h,"cookie":cookie},b"{}")
            self.assertEqual(out.status_code,200)
            self.assertEqual(self.invoke("/admin/api/status","GET",{"cookie":cookie}).status_code,401)
if __name__=="__main__":unittest.main()
