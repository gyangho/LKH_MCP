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
            self.assertEqual(get_allowed_tables(), {"SAFE", "ITAM.ASSET_1"})
            with self.assertRaises(PermissionError):
                preview_table("UNLISTED")  # denied BEFORE any connection is made


if __name__ == "__main__":
    unittest.main()
