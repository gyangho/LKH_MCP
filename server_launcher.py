"""Entry point for LKH MCP Windows no-console executable."""
import logging
import os
import sys
from pathlib import Path

def main():
    from dotenv import load_dotenv
    home = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    load_dotenv(home / ".env", override=False)
    base = Path(os.getenv("MCP_STATE_DIR") or (Path(os.getenv("LOCALAPPDATA") or Path.home()) / "LKH_MCP"))
    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    output = (logs / "server.log").open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None: sys.stdout = output
    if sys.stderr is None: sys.stderr = output
    logging.basicConfig(filename=str(logs / "server.log"), level=logging.INFO)
    try:
        from server import run
        run()
    except BaseException:
        logging.exception("LKH MCP startup failed")
        raise

if __name__ == "__main__":
    main()
