"""Increment the native patch version once per build invocation (under the build lock)."""
from pathlib import Path
import os
import re
import uuid


def write_atomic(path, text):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    root = Path(__file__).resolve().parent.parent
    version_file = root / "src/version.py"
    source = version_file.read_text(encoding="utf-8")
    match = re.search(r'^VERSION = "([0-9]+)\.([0-9]+)\.([0-9]+)"$', source, re.MULTILINE)
    if match is None:
        raise RuntimeError("Native version must be major.minor.patch")
    major, minor, patch = map(int, match.groups())
    patch += 1
    if patch > 65535:
        minor, patch = minor + 1, 0
    if minor > 65535:
        major, minor = major + 1, 0
    if major > 65535:
        raise RuntimeError("Windows version number exhausted")
    version = f"{major}.{minor}.{patch}"
    updated = source[:match.start()] + f'VERSION = "{version}"' + source[match.end():]
    resource = f"""VSVersionInfo(
 ffi=FixedFileInfo(filevers=({major},{minor},{patch},0),prodvers=({major},{minor},{patch},0),
   mask=0x3f,flags=0x0,OS=0x40004,fileType=0x1,subtype=0x0,date=(0,0)),
 kids=[
   StringFileInfo([StringTable('040904B0',[
     StringStruct('CompanyName','LKH'),
     StringStruct('FileDescription','LKH MCP'),
     StringStruct('FileVersion','{version}'),
     StringStruct('ProductName','LKH MCP'),
     StringStruct('ProductVersion','{version}')])]),
   VarFileInfo([VarStruct('Translation',[1033,1200])])
 ])
"""
    write_atomic(root / "scripts/windows-version.txt", resource)
    write_atomic(root / "installer/version.iss", f'#define AppVersion "{version}"\n')
    write_atomic(version_file, updated)
    print("Native build version: " + version)


if __name__ == "__main__":
    main()
