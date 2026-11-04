"""Installed local AST-only worker. No skill registration, Codex login or model API."""
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    from public_skills import skill_paths
    paths = skill_paths("graphify", root=root)
    if paths is None or len(sys.argv) != 2:
        raise RuntimeError("Graphify installation or invocation invalid")
    checkout = Path(sys.argv[1]).resolve(strict=True)
    if not (checkout / ".git").exists():
        raise RuntimeError("Git worktree required")
    os.chdir(checkout)
    # Isolated interpreter and sanitized Agent environment; all writes stay in worktree.
    sys.path.insert(0, str(paths["source"] / "deps"))
    sys.path.insert(0, str(paths["source"]))
    os.environ["PYTHONHASHSEED"] = "0"
    os.environ["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"
    os.environ["GRAPHIFY_OUT"] = "graphify-out"
    sys.argv = ["graphify", "extract", ".", "--code-only", "--no-cluster", "--max-workers", "1", "--force"]
    from graphify.__main__ import main as extract
    extract()
    graph = checkout / "graphify-out/graph.json"
    if not graph.is_file():
        raise RuntimeError("Graphify did not create graph.json")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()
