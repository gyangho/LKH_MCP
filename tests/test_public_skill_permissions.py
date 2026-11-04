"""Windows ACL regression for sources moved out of tempfile's private tree."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "install_public_skills", Path(__file__).resolve().parents[1] / "scripts/install-public-skills.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@unittest.skipUnless(os.name == "nt", "Windows ACLs required")
class PublicSkillPermissionsTests(unittest.TestCase):
    def test_published_source_inherits_read_access_from_skills_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            skills = Path(folder) / "skills"
            skills.mkdir()
            subprocess.run(["icacls.exe", str(skills), "/grant",
                            "*S-1-5-19:(OI)(CI)RX"], check=True, capture_output=True)
            with tempfile.TemporaryDirectory(dir=skills) as staging:
                source = Path(staging) / "source"
                source.mkdir()
                script = source / "nested/search.py"
                script.parent.mkdir()
                script.write_text("# public source", encoding="utf-8")
                destination = skills / "uiux-test"
                source.rename(destination)
                installer.restore_source_permissions(destination, skills)
                # Assert actual inherited LocalService access on root AND leaf.
                for path in (destination, destination / "nested/search.py"):
                    result = subprocess.run([
                        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        "$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath $env:LKH_TEST_ACL_PATH; "
                        "@($acl.Access | Where-Object { "
                        "$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value "
                        "-eq 'S-1-5-19' -and $_.IsInherited -and "
                        "$_.AccessControlType -eq 'Allow' -and "
                        "($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::ReadAndExecute) "
                        "-eq [Security.AccessControl.FileSystemRights]::ReadAndExecute }).Count"],
                        env={**{key: value for key, value in os.environ.items()
                                if key.lower() != "psmodulepath"}, "LKH_TEST_ACL_PATH": str(path)},
                        check=True, capture_output=True, text=True)
                    self.assertGreater(int(result.stdout.strip()), 0)

    def test_rejects_source_outside_skills(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "skills").mkdir()
            with self.assertRaises(ValueError):
                installer.restore_source_permissions(root, root / "skills")
