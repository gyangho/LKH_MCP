"""Validated installer network settings shared by the server and local clients."""
from __future__ import annotations

import configparser
import ipaddress
import os
import secrets
from pathlib import Path

DEFAULTS = {"host": "127.0.0.1", "mcp_port": "8000", "admin_port": "8001"}


def validate(host: str, mcp_port: str, admin_port: str) -> dict[str, str]:
    try:
        address = ipaddress.IPv4Address(host)
    except (ValueError, TypeError) as exc:
        raise ValueError("MCP IP must be a specific IPv4 address") from exc
    if address.is_unspecified or address.is_multicast or str(address) == "255.255.255.255":
        raise ValueError("MCP IP must be a specific unicast IPv4 address")
    for port in (mcp_port, admin_port):
        if not isinstance(port, str) or not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError("Ports must be integers from 1 to 65535")
    if int(mcp_port) == int(admin_port):
        raise ValueError("MCP and Admin ports must differ")
    return {"host": str(address), "mcp_port": str(int(mcp_port)), "admin_port": str(int(admin_port))}


def config_path(root: Path | None = None, env=None) -> Path:
    from native_runtime import native_state_dir
    return native_state_dir(env=env, root=root) / "config" / "network.ini"


def load(root: Path | None = None, env=None) -> dict[str, str]:
    path = config_path(root, env)
    if not path.exists():
        return dict(DEFAULTS)
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(path.read_text(encoding="utf-8-sig"))
    if parser.sections() != ["network"] or set(parser["network"]) != set(DEFAULTS):
        raise ValueError("Invalid native network configuration")
    return validate(**dict(parser["network"]))


def save(host: str, mcp_port: str, admin_port: str, *, root: Path | None = None) -> None:
    settings = validate(host, mcp_port, admin_port)
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("network-" + secrets.token_hex(12) + ".tmp")
    parser = configparser.ConfigParser(interpolation=None)
    parser["network"] = settings
    try:
        with temporary.open("x", encoding="utf-8") as output:
            parser.write(output)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def admin_base() -> str:
    # Tray and uninstall/Agent helpers always use the private local listener.
    settings = load()
    port = os.getenv("LKH_NATIVE_ADMIN_PORT") or settings["admin_port"]
    validate(settings["host"], settings["mcp_port"], port)
    return "http://127.0.0.1:" + str(int(port))
