"""Non-destructive SQLite backup and comparison for Docker -> Native staging.

The source can be an exported SQLite DB file or a safely mounted snapshot.
This tool never edits or deletes the source, never overwrites a destination,
and does NOT perform production cutover or Cloudflare changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import quote


def inspect_database(path: Path) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Source SQLite file not found")
    uri = "file:" + quote(str(path).replace("\\", "/"), safe="/:") + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=15) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("SQLite integrity check failed")
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        counts = {}
        for name in tables:
            quoted = '"' + name.replace('"', '""') + '"'
            counts[name] = db.execute("SELECT COUNT(*) FROM " + quoted).fetchone()[0]
        return {"integrity": "ok", "tables": counts, "bytes": path.stat().st_size}


def copy_snapshot(source: Path, destination: Path) -> dict:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError("Source and destination must differ")
    if not source.is_file():
        raise FileNotFoundError("Source SQLite file missing")
    if destination.exists():
        raise FileExistsError("Destination exists: refuse overwrite")
    if not destination.parent.is_dir():
        raise FileNotFoundError("Destination parent must already exist")
    original = inspect_database(source)
    temporary = destination.parent / (destination.name + "." + uuid.uuid4().hex + ".partial")
    uri = "file:" + quote(str(source).replace("\\", "/"), safe="/:") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=15) as src:
            with sqlite3.connect(str(temporary), timeout=15) as dst:
                src.backup(dst, pages=128, sleep=0.1)
        migrated = inspect_database(temporary)
        if migrated["tables"] != original["tables"]:
            raise RuntimeError("Table row-count mismatch after backup")
        # Fail closed if someone creates destination during backup.
        with destination.open("xb"):
            pass
        try:
            os.replace(temporary, destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return {"source": str(source), "destination": str(destination),
                "source_tables": original["tables"], "copied_tables": migrated["tables"],
                "integrity": migrated["integrity"]}
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="SQLite non-destructive staging snapshot")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args(argv)
    if args.copy:
        if not args.destination:
            parser.error("--copy requires --destination")
        result = copy_snapshot(args.source, args.destination)
    else:
        result = inspect_database(args.source)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
