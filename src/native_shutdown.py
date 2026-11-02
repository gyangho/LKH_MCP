"""Process-local, Native-only graceful shutdown coordinator.

An administrator action schedules shutdown *after* the HTTP acknowledgement.
Nothing here can control Docker, Naru, arbitrary services, or another process.
"""
from __future__ import annotations

import asyncio
import os

_stop_event: asyncio.Event | None = None


def arm(event: asyncio.Event) -> None:
    global _stop_event
    if os.environ.get("LKH_NATIVE_MODE") != "1":
        raise RuntimeError("Native shutdown is unavailable")
    _stop_event = event


def schedule_shutdown(delay: float = 0.75) -> None:
    if os.environ.get("LKH_NATIVE_MODE") != "1" or _stop_event is None:
        raise RuntimeError("Native server shutdown is not armed")
    if not 0.2 <= delay <= 5:
        raise ValueError("Invalid shutdown delay")

    async def finish() -> None:
        await asyncio.sleep(delay)
        if _stop_event is not None:
            _stop_event.set()
    asyncio.get_running_loop().create_task(finish())
