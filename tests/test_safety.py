import os
import unittest
from unittest.mock import patch
from oracle_db import validate_identifier, validate_table_reference, get_allowed_tables, preview_table


class GuardTests(unittest.TestCase):
    def test_identifiers(self):
        self.assertEqual(validate_identifier("asset_1"), "ASSET_1")
        for payload in ["USERS;DROP TABLE X", "A.B", '"T"', "A B", "", "A" * 31]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    validate_identifier(payload)

    def test_allowlist(self):
        self.assertEqual(validate_table_reference("ITAM.Asset_1"), "ITAM.ASSET_1")
        for bad in ["X.Y.Z", "X;DELETE", 'X."TABLE"']:
            with self.assertRaises(ValueError):
                validate_table_reference(bad)
        with patch.dict(os.environ, {"ORACLE_ALLOWED_TABLES": "safe, ITAM.Asset_1"}):
            self.assertEqual(get_allowed_tables("safe, ITAM.Asset_1"), {"SAFE", "ITAM.ASSET_1"})
            with patch("oracle_db._profile", return_value={"allowed_tables": "SAFE"}):
                with self.assertRaises(PermissionError):
                    preview_table("connection-id", "UNLISTED")  # denied BEFORE opening Oracle


if __name__ == "__main__":
    unittest.main()
