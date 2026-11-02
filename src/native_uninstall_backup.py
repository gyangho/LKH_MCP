"""Verified WAL-aware SQLite recovery snapshot before Native full uninstall."""
from __future__ import annotations
import argparse
from pathlib import Path
from native_migration import copy_snapshot

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="LKH MCP Native removal snapshot")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args(argv)
    result = copy_snapshot(args.source, args.destination)
    if result["integrity"] != "ok" or not result["logical_sha256"]:
        raise RuntimeError("SQLite integrity verification failed")
    print("Verified SQLite recovery snapshot created.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
