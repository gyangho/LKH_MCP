"""Interactive first-run administrator bootstrap without command-line passwords.

The installer runs this in a visible Windows console exactly once. Passwords
are entered via getpass and only a slow salted hash enters protected ProgramData.
Existing bootstrap.json is preserved without modification.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
from pathlib import Path


def initialize(*, username: str = "admin", root: Path | None = None,
               password: str | None = None) -> dict:
    from native_runtime import native_state_dir
    from admin_auth import make_password_hash
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", username):
        raise ValueError("Invalid administrator username")
    target_root = native_state_dir(root=root)
    config = target_root / "config"
    config.mkdir(parents=True, exist_ok=True)
    target = config / "bootstrap.json"
    if target.exists():
        return {"configured": True, "unchanged": True}
    if password is None:
        password = getpass.getpass("Create LKH MCP administrator password (14+ chars): ")
        confirm = getpass.getpass("Repeat administrator password: ")
        if password != confirm:
            raise ValueError("Passwords differ")
    if not 14 <= len(password) <= 256:
        raise ValueError("Administrator password must be at least 14 characters")
    content = {
        "ADMIN_LOGIN_USER": username,
        "ADMIN_PASSWORD_HASH": make_password_hash(password),
        "ADMIN_PUBLIC_ORIGIN": "http://127.0.0.1:18081",
    }
    temporary = config / ("bootstrap-" + secrets.token_hex(12) + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as out:
            json.dump(content, out, ensure_ascii=False)
        if target.exists():
            raise FileExistsError("Another process configured the administrator")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"configured": True, "unchanged": False}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--initialize", action="store_true")
    args = parser.parse_args(argv)
    if os.name != "nt" or not args.initialize:
        parser.error("Windows interactive administrator setup required")
    result = initialize()
    print("LKH MCP administrator configured." if not result["unchanged"]
          else "Existing administrator bootstrap preserved.")


if __name__ == "__main__":
    main()
