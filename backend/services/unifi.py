"""UniFi API client — clients, devices, and health."""

from __future__ import annotations
import asyncio
import logging
import time
import httpx
from cachetools import TTLCache
from config import settings

logger = logging.getLogger(__name__)

_cache: TTLCache = TTLCache(maxsize=10, ttl=60)
_cookies: dict = {}
_client: httpx.AsyncClient | None = None
_login_lock: asyncio.Lock | None = None
_last_login_attempt: float = 0
_LOGIN_COOLDOWN = 30  # seconds between login attempts to avoid 429


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(verify=False, timeout=15.0)
    return _client


async def _login() -> None:
    global _cookies, _login_lock, _last_login_attempt
    if _login_lock is None:
        _login_lock = asyncio.Lock()
    async with _login_lock:
        # If another coroutine already logged in while we waited, skip
        if _cookies:
            return
        # Rate-limit login attempts to avoid 429
        elapsed = time.time() - _last_login_attempt
        if elapsed < _LOGIN_COOLDOWN:
            raise httpx.HTTPStatusError(
                f"Login cooldown ({_LOGIN_COOLDOWN - elapsed:.0f}s remaining)",
                request=httpx.Request("POST", settings.unifi_url),
                response=httpx.Response(429),
            )
        _last_login_attempt = time.time()
        c = await _get_client()
        r = await c.post(
            f"{settings.unifi_url}/api/auth/login",
            json={"username": settings.unifi_username, "password": settings.unifi_password},
        )
        r.raise_for_status()
        _cookies = dict(r.cookies)


async def _get(path: str) -> list:
    if not settings.unifi_url or not settings.enable_unifi:
        return []
    global _cookies
    if not _cookies:
        await _login()
    c = await _get_client()
    r = await c.get(f"{settings.unifi_url}{path}", cookies=_cookies)
    if r.status_code == 401:
        _cookies = {}  # clear stale cookies so _login() knows to re-auth
        await _login()
        r = await c.get(f"{settings.unifi_url}{path}", cookies=_cookies)
    r.raise_for_status()
    return r.json().get("data", [])


async def get_clients() -> dict:
    if "clients" in _cache:
        return _cache["clients"]

    try:
        # Fetch both clients and devices so we can resolve AP names
        data = await _get("/proxy/network/api/s/default/stat/sta")
        devices = await _get("/proxy/network/api/s/default/stat/device")
    except Exception:
        logger.exception("Failed to fetch UniFi clients")
        return {"total": 0, "by_vlan": {}, "fetched_at": int(time.time()), "error": "UniFi API unavailable"}

    # Build AP MAC -> name map
    ap_names: dict[str, str] = {}
    for dev in devices:
        if dev.get("type") == "uap":
            ap_names[dev.get("mac", "")] = dev.get("name", dev.get("hostname", "Unknown AP"))

    by_vlan: dict[str, list] = {}
    for client in data:
        vlan_name = client.get("network", "Unknown")
        vlan_id = client.get("vlan", 0)

        entry = {
            "name": client.get("name", client.get("hostname", client.get("oui", "Unknown"))),
            "ip": client.get("ip", "N/A"),
            "mac": client.get("mac", ""),
            "vlan_id": vlan_id,
            "vlan_name": vlan_name,
            "connection": "wireless" if client.get("is_wired") is False else "wired",
            "ap_name": ap_names.get(client.get("ap_mac", ""), ""),
            "essid": client.get("essid", ""),
            "uptime": client.get("uptime", 0),
            "rx_bytes": client.get("rx_bytes", 0),
            "tx_bytes": client.get("tx_bytes", 0),
            "signal": client.get("signal", 0),
            "score": client.get("score", -1),
            "channel": client.get("channel", 0),
        }
        by_vlan.setdefault(vlan_name, []).append(entry)

    result = {
        "total": len(data),
        "by_vlan": {k: sorted(v, key=lambda x: x["name"]) for k, v in sorted(by_vlan.items())},
        "fetched_at": int(time.time()),
    }
    _cache["clients"] = result
    return result


async def get_health() -> dict:
    if "health" in _cache:
        return _cache["health"]

    try:
        data = await _get("/proxy/network/api/s/default/stat/health")
    except Exception:
        logger.exception("Failed to fetch UniFi health")
        return {"subsystems": {}, "fetched_at": int(time.time()), "error": "UniFi API unavailable"}

    subsystems = {}
    for sub in data:
        name = sub.get("subsystem", "unknown")
        subsystems[name] = {
            "status": sub.get("status", "unknown"),
            "num_user": sub.get("num_user", 0),
            "num_guest": sub.get("num_guest", 0),
            "num_iot": sub.get("num_iot", 0),
            "tx_bytes_r": sub.get("tx_bytes-r", 0),
            "rx_bytes_r": sub.get("rx_bytes-r", 0),
            "num_ap": sub.get("num_ap", 0),
            "num_adopted": sub.get("num_adopted", 0),
            "num_disabled": sub.get("num_disabled", 0),
            "num_disconnected": sub.get("num_disconnected", 0),
            "num_pending": sub.get("num_pending", 0),
            "num_gateways": sub.get("num_gateways", 0),
            "num_switches": sub.get("num_switches", 0),
            "gw_version": sub.get("gw_version", ""),
            "latency": sub.get("latency", 0),
            "speedtest_status": sub.get("speedtest_status", ""),
            "speedtest_ping": sub.get("speedtest_ping", 0),
            "xput_up": sub.get("xput_up", 0),
            "xput_down": sub.get("xput_down", 0),
        }

    result = {"subsystems": subsystems, "fetched_at": int(time.time())}
    _cache["health"] = result
    return result


def _fmt_uptime(s):
    if not s:
        return "--"
    h = s // 3600
    d = h // 24
    if d > 0:
        return f"{d}d {h % 24}h"
    return f"{h}h {(s % 3600) // 60}m"


async def get_devices() -> dict:
    if "devices" in _cache:
        return _cache["devices"]

    try:
        data = await _get("/proxy/network/api/s/default/stat/device")
    except Exception:
        logger.exception("Failed to fetch UniFi devices")
        return {"gateways": [], "switches": [], "aps": [], "fetched_at": int(time.time()), "error": "UniFi API unavailable"}

    gateways, switches, aps = [], [], []

    for dev in data:
        dt = dev.get("type", "")
        model = dev.get("model", "")
        base = {
            "name": dev.get("name", dev.get("hostname", model)),
            "ip": dev.get("ip", ""),
            "mac": dev.get("mac", ""),
            "model": model,
            "version": dev.get("version", ""),
            "upgradable": dev.get("upgradable", False),
            "upgrade_to_firmware": dev.get("upgrade_to_firmware", ""),
            "uptime": _fmt_uptime(dev.get("uptime", 0)),
            "uptime_s": dev.get("uptime", 0),
            "state": dev.get("state", 0),
            "adopted": dev.get("adopted", False),
            "cpu_pct": round(float(dev.get("system-stats", {}).get("cpu", 0) or 0)),
            "mem_pct": round(float(dev.get("system-stats", {}).get("mem", 0) or 0)),
            "tx_bytes_r": dev.get("tx_bytes-r", 0),
            "rx_bytes_r": dev.get("rx_bytes-r", 0),
            "num_sta": dev.get("num_sta", 0),
            "satisfaction": dev.get("satisfaction", -1),
        }

        if dt in ("ugw", "udm", "udmpro", "uxg"):
            wan = dev.get("uplink", {})
            base["wan_ip"] = wan.get("ip", "")
            base["wan_name"] = wan.get("name", "")
            base["wan_speed"] = wan.get("speed", 0)
            base["wan_full_duplex"] = wan.get("full_duplex", False)
            gateways.append(base)
        elif dt in ("usw",):
            ports = dev.get("port_table", [])
            base["port_count"] = len(ports)
            base["ports_up"] = sum(1 for p in ports if p.get("up"))
            base["poe_budget"] = dev.get("total_max_power", 0)
            base["ports"] = [
                {
                    "idx": p.get("port_idx", i + 1),
                    "up": p.get("up", False),
                    "speed": p.get("speed", 0),
                    "poe_enable": p.get("poe_enable", False),
                    "poe_power": round(float(p.get("poe_power", 0) or 0), 1),
                    "name": p.get("name", f"Port {i+1}"),
                    "media": p.get("media", ""),
                }
                for i, p in enumerate(ports)
            ]
            switches.append(base)
        elif dt in ("uap",):
            radios = dev.get("radio_table_stats", [])
            radio_info = []
            for r in radios:
                radio_info.append({
                    "band": r.get("radio", ""),
                    "channel": r.get("channel", 0),
                    "num_sta": r.get("num_sta", 0),
                    "satisfaction": r.get("satisfaction", -1),
                    "tx_power": r.get("tx_power", 0),
                    "cu_self_rx": r.get("cu_self_rx", 0),
                    "cu_self_tx": r.get("cu_self_tx", 0),
                    "cu_total": r.get("cu_total", 0),
                })
            base["radios"] = radio_info
            base["vap_table"] = [
                {"essid": v.get("essid", ""), "num_sta": v.get("num_sta", 0)}
                for v in dev.get("vap_table", [])
            ]
            aps.append(base)

    result = {
        "gateways": gateways,
        "switches": switches,
        "aps": sorted(aps, key=lambda x: x["name"]),
        "fetched_at": int(time.time()),
    }
    _cache["devices"] = result
    return result


async def get_alarms() -> list:
    if "alarms" in _cache:
        return _cache["alarms"]
    try:
        data = await _get("/proxy/network/api/s/default/rest/alarm?archived=false")
        result = [
            {
                "key": a.get("key", ""),
                "msg": a.get("msg", ""),
                "datetime": a.get("datetime", ""),
                "site_id": a.get("site_id", ""),
                "subsystem": a.get("subsystem", ""),
            }
            for a in data[:20]
        ]
    except Exception:
        logger.exception("Failed to fetch UniFi alarms")
        result = []
    _cache["alarms"] = result
    return result
