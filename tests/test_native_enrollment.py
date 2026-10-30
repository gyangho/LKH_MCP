"""DPAPI-protected local device enrollment verifier tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import native_enrollment as enrollment


class EnrollmentTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "staging"
        # Use a reversible test-only codec: the actual Windows provider is DPAPI.
        for mocker in (
            patch.object(enrollment, "_protect", side_effect=lambda data: data[::-1]),
            patch.object(enrollment, "_unprotect", side_effect=lambda data: data[::-1]),
        ):
            mocker.start()
            self.addCleanup(mocker.stop)

    def test_initial_provision_and_session(self):
        first = enrollment.provision(self.root)
        self.assertEqual(first["generation"], 1)
        self.assertTrue(enrollment.enrolled(self.root))
        secret = enrollment.read_device_secret(self.root)
        self.assertGreaterEqual(len(secret), 48)
        token = enrollment.issue_session(secret, self.root)["access_token"]
        self.assertTrue(enrollment.check_access("Bearer " + token, self.root))
        self.assertFalse(enrollment.check_access("Bearer " + "bad" * 20, self.root))
        self.assertTrue(enrollment.provision(self.root)["unchanged"])
        database = self.root / "data" / "mcp.sqlite3"
        self.assertNotIn(secret.encode("ascii"), database.read_bytes())
        self.assertNotIn(token.encode("ascii"), database.read_bytes())

    def test_rotation_is_automatic_and_revokes_old_sessions(self):
        enrollment.provision(self.root)
        old = enrollment.read_device_secret(self.root)
        token = enrollment.issue_session(old, self.root)["access_token"]
        rotated = enrollment.provision(self.root, rotate=True)
        self.assertEqual(rotated["generation"], 2)
        self.assertFalse(enrollment.check_access("Bearer " + token, self.root))
        with self.assertRaises(PermissionError):
            enrollment.issue_session(old, self.root)
        fresh = enrollment.read_device_secret(self.root)
        self.assertNotEqual(old, fresh)
        self.assertTrue(enrollment.check_access(
            "Bearer " + enrollment.issue_session(fresh, self.root)["access_token"], self.root))

    def test_rotation_rolls_back_credential_if_sql_update_fails(self):
        enrollment.provision(self.root)
        old_secret = enrollment.read_device_secret(self.root)
        old_token = enrollment.issue_session(old_secret, self.root)["access_token"]
        with patch.object(enrollment.time, "time", side_effect=RuntimeError("forced failure")):
            with self.assertRaises(RuntimeError):
                enrollment.provision(self.root, rotate=True)
        self.assertEqual(enrollment.read_device_secret(self.root), old_secret)
        self.assertTrue(enrollment.check_access("Bearer " + old_token, self.root))

    def test_existing_registration_requires_credential_file(self):
        enrollment.provision(self.root)
        path = self.root / "config" / "agent-credential.bin"
        path.unlink()
        with self.assertRaises(RuntimeError):
            enrollment.provision(self.root)

    def test_orphaned_enrollment_refused(self):
        path = self.root / "config" / "agent-credential.bin"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"orphan")
        with self.assertRaises(RuntimeError):
            enrollment.provision(self.root)

    def test_invalid_tokens_and_expiration(self):
        enrollment.provision(self.root)
        secret = enrollment.read_device_secret(self.root)
        token = enrollment.issue_session(secret, self.root)["access_token"]
        with patch.object(enrollment.time, "time", return_value=2**40):
            self.assertFalse(enrollment.check_access("Bearer " + token, self.root))
        for header in ("", "Device " + secret, "Bearer " + "1"*300):
            self.assertFalse(enrollment.check_access(header, self.root))


if __name__ == "__main__":
    unittest.main()
