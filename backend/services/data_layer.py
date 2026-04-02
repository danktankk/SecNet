"""Abstract data layer — all external queries go through here.
Swap implementations to migrate to InfluxDB/Prometheus storage later."""

from __future__ import annotations
import asyncio
import logging
import time
from typing import Any
import httpx
from cachetools import TTLCache

logger = logging.getLogger(__name__)
from config import settings

_client: httpx.AsyncClient | None = None
_geo_cache: TTLCache = TTLCache(maxsize=10000, ttl=86400)
_geo_semaphore = asyncio.Semaphore(2)

# CrowdSec machine auth (JWT for alerts endpoint)
_cs_jwt: str = ""
_cs_jwt_expires: float = 0


async def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


# ── CrowdSec ──────────────────────────────────────────────

async def crowdsec_get(path: str, params: dict | None = None) -> Any:
    """Bouncer API — for decisions."""
    if not settings.crowdsec_url or not settings.enable_crowdsec:
        raise ValueError("CrowdSec not configured")
    c = await client()
    headers = {"X-Api-Key": settings.crowdsec_api_key}
    r = await c.get(f"{settings.crowdsec_url}{path}", headers=headers, params=params)
    r.raise_for_status()
    return r.json()


async def _cs_machine_token() -> str:
    """Get a JWT for CrowdSec LAPI machine auth (alerts endpoint)."""
    global _cs_jwt, _cs_jwt_expires
    if _cs_jwt and time.time() < _cs_jwt_expires - 60:
        return _cs_jwt
    if not settings.crowdsec_machine_id or not settings.crowdsec_machine_password:
        return ""
    c = await client()
    r = await c.post(f"{settings.crowdsec_url}/v1/watchers/login", json={
        "machine_id": settings.crowdsec_machine_id,
        "password": settings.crowdsec_machine_password,
    })
    r.raise_for_status()
    data = r.json()
    _cs_jwt = data.get("token", "")
    # Parse expire time, default 1 hour
    try:
        from datetime import datetime
        exp = datetime.fromisoformat(data["expire"].replace("Z", "+00:00"))
        _cs_jwt_expires = exp.timestamp()
    except Exception:
        _cs_jwt_expires = time.time() + 3600
    return _cs_jwt


async def crowdsec_alerts_get(path: str, params: dict | None = None) -> Any:
    """Machine auth — for alerts endpoint."""
    if not settings.crowdsec_url or not settings.enable_crowdsec:
        raise ValueError("CrowdSec not configured")
    token = await _cs_machine_token()
    if not token:
        raise ValueError("CrowdSec machine credentials not configured")
    c = await client()
    r = await c.get(f"{settings.crowdsec_url}{path}", headers={"Authorization": f"Bearer {token}"}, params=params)
    r.raise_for_status()
    return r.json()


async def get_decisions() -> list[dict]:
    try:
        data = await crowdsec_get("/v1/decisions/stream", {"startup": "true"})
        return data.get("new") or []
    except ValueError:
        return []
    except Exception:
        logger.exception("Failed to fetch decisions")
        return []


async def get_alerts(since: str = "1h") -> list[dict]:
    try:
        return await crowdsec_alerts_get("/v1/alerts", {"since": since})
    except ValueError:
        return []
    except Exception:
        logger.exception("Failed to fetch alerts")
        return []


# ── Loki ──────────────────────────────────────────────────

async def loki_query(query: str, limit: int = 100, since_ns: int | None = None) -> list[dict]:
    if not settings.loki_url or not settings.enable_loki:
        return []
    c = await client()
    params: dict[str, Any] = {"query": query, "limit": str(limit), "direction": "backward"}
    if since_ns:
        params["start"] = str(since_ns)
    else:
        params["start"] = str((int(time.time()) - 86400) * 10**9)
    params["end"] = str(int(time.time()) * 10**9)
    try:
        r = await c.get(f"{settings.loki_url}/loki/api/v1/query_range", params=params)
        r.raise_for_status()
        data = r.json()
        results = data.get("data", {}).get("result", [])
        entries = []
        for stream in results:
            labels = stream.get("stream", {})
            for ts, line in stream.get("values", []):
                entries.append({"timestamp": ts, "line": line, "labels": labels})
        return entries
    except Exception:
        logger.exception("Failed to fetch Loki query")
        return []


async def loki_count(query: str, range_seconds: int = 86400) -> int:
    if not settings.loki_url or not settings.enable_loki:
        return 0
    c = await client()
    count_query = f'count_over_time({query}[{range_seconds}s])'
    try:
        r = await c.get(f"{settings.loki_url}/loki/api/v1/query", params={"query": count_query})
        r.raise_for_status()
        results = r.json().get("data", {}).get("result", [])
        return sum(int(float(v[1])) for v in [r.get("value", [0, "0"]) for r in results])
    except Exception:
        logger.exception("Failed to fetch Loki count")
        return 0


# ── Prometheus ────────────────────────────────────────────

async def prom_query(query: str) -> list[dict]:
    if not settings.prometheus_url or not settings.enable_prometheus:
        return []
    c = await client()
    try:
        r = await c.get(f"{settings.prometheus_url}/api/v1/query", params={"query": query})
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception:
        logger.exception("Failed to fetch Prometheus query")
        return []


async def prom_query_range(query: str, start: int, end: int, step: str = "300") -> list[dict]:
    if not settings.prometheus_url or not settings.enable_prometheus:
        return []
    c = await client()
    try:
        r = await c.get(f"{settings.prometheus_url}/api/v1/query_range", params={
            "query": query, "start": str(start), "end": str(end), "step": step
        })
        r.raise_for_status()
        return r.json().get("data", {}).get("result", [])
    except Exception:
        logger.exception("Failed to fetch Prometheus range query")
        return []


# ── GeoIP ─────────────────────────────────────────────────

async def geoip_lookup(ip: str) -> dict | None:
    if ip in _geo_cache:
        return _geo_cache[ip]
    async with _geo_semaphore:
        if ip in _geo_cache:
            return _geo_cache[ip]
        c = await client()
        try:
            r = await c.get(f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,city,lat,lon,isp,org,as")
            if r.status_code == 429:
                await asyncio.sleep(1)
                return None
            data = r.json()
            if data.get("status") == "success":
                _geo_cache[ip] = data
                return data
        except Exception:
            logger.exception("Failed to fetch GeoIP lookup for %s", ip)
    return None


async def geoip_batch(ips: list[str]) -> dict[str, dict]:
    results = {}
    to_lookup = [ip for ip in set(ips) if ip not in _geo_cache]
    cached = {ip: _geo_cache[ip] for ip in set(ips) if ip in _geo_cache}
    results.update(cached)

    if to_lookup:
        c = await client()
        for i in range(0, len(to_lookup), 100):
            batch = to_lookup[i:i+100]
            try:
                r = await c.post("http://ip-api.com/batch?fields=status,query,country,countryCode,city,lat,lon,isp,org,as", json=batch)
                if r.status_code == 200:
                    for item in r.json():
                        if item.get("status") == "success":
                            ip = item["query"]
                            _geo_cache[ip] = item
                            results[ip] = item
                if i + 100 < len(to_lookup):
                    await asyncio.sleep(1.5)
            except Exception:
                logger.exception("Failed to fetch GeoIP batch")
    return results
