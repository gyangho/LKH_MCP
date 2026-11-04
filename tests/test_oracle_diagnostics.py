"""Safe error codes from the actual driver boundary, never connection details."""
import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import oracle_db

class DiagnosticTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows OCI DLL search")
    def test_explicit_client_directory_precedes_frozen_dll_search_path(self):
        with tempfile.TemporaryDirectory() as directory:
            client = str(Path(directory).resolve())
            driver = MagicMock()
            def initialize(**kwargs):
                self.assertEqual(kwargs, {"lib_dir": client})
                self.assertEqual(os.environ["PATH"].split(os.pathsep), [client, "other"])
            driver.init_oracle_client.side_effect = initialize
            with patch.dict(os.environ, {"ORACLE_CLIENT_LIB_DIR": client,
                                          "PATH": "other" + os.pathsep + client}), \
                    patch.object(oracle_db, "_oracledb", driver), \
                    patch.object(oracle_db, "_client_initialized", False):
                self.assertIs(oracle_db._driver(), driver)
                self.assertIs(oracle_db._driver(), driver)
                driver.init_oracle_client.assert_called_once()

    def test_driver_failure_exposes_only_code(self):
        for error, expected in (("ORA-01017: password=secret host=private", "ORA-01017"),
                                ("DPI-1047: private-path", "DPI-1047"),
                                ("password=secret", "UNCLASSIFIED")):
            driver = MagicMock()
            driver.connect.side_effect = RuntimeError(error)
            profile = dict(username="private", password="secret", dsn="private", service="", sid="")
            with patch.object(oracle_db, "_driver", return_value=driver):
                with self.assertRaises(oracle_db.OracleUnavailable) as caught:
                    with oracle_db.connection(profile):
                        pass
            self.assertEqual(str(caught.exception), "Oracle connection or query failed [" + expected + "]")

if __name__ == "__main__": unittest.main()
