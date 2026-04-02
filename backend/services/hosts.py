"""Infrastructure host registry — all non-Proxmox managed hosts with live health checks."""

from __future__ import annotations
import asyncio
import time
from cachetools import TTLCache
from db import get_host_registry

_cache: TTLCache = TTLCache(maxsize=1, ttl=30)


def get_registry() -> list[dict]:
    """Load the host registry from SQLite."""
    return get_host_registry()


async def _tcp_ping(ip: str, port: int, timeout: float = 1.5) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port), timeout=timeout
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def get_hosts() -> list[dict]:
    """Return all infrastructure hosts with live TCP health status. Cached 30s."""
    if "hosts" in _cache:
        return _cache["hosts"]

    registry = get_registry()
    checks = [
        asyncio.sleep(0) if h.get("skip_check") else _tcp_ping(h["ip"], h["check_port"])
        for h in registry
    ]
    results = await asyncio.gather(*checks)

    hosts = []
    for host, result in zip(registry, results):
        hosts.append({
            **host,
            "online": False if host.get("skip_check") else bool(result),
            "checked_at": int(time.time()),
        })

    _cache["hosts"] = hosts
    return hosts
