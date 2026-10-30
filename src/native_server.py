"""I1 native server entrypoint: separate from interactive system tray.

Not a Windows SCM service (I2). The combined MCP/admin app runs on loopback
for staging only. No network bind is opened by --check.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from native_runtime import prepare_native_environment, required_assets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LKH MCP native Windows server preview")
    parser.add_argument("--check", action="store_true", help="check packaged assets and exit, without starting server")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("Native server entrypoint is supported only on Windows")
    # Check assets first: no state directory is mutated if the bundle is incomplete.
    assets = required_assets()
    missing = [name for name, present in assets.items() if not present]
    if missing:
        print("Native bundle missing: " + ", ".join(missing), file=sys.stderr)
        return 2
    if args.check:
        print("Native bundle assets: OK")
        print("Service registration, Oracle connectivity, UIUX Python runtime and network access: NOT VERIFIED")
        return 0
    state = prepare_native_environment()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(state / "logs" / "server.log", encoding="utf-8")],
    )
    logging.info("Native preview starting (loopback only); not a Windows Service")
    import asyncio
    from server import mcp
    from native_gateway import run_native_gateways
    asyncio.run(run_native_gateways(
        mcp, host=os.environ["MCP_HOST"], mcp_port=int(os.environ["MCP_PORT"]),
        admin_port=int(os.environ["LKH_NATIVE_ADMIN_PORT"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
