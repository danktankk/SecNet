"""Environment discovery — three-layer scan to detect available integrations.

Layer 1: Config audit  — current settings state vs what's missing.
Layer 2: Gateway probe — detect known router/firewall types at the default gateway.
Layer 3: Subnet sweep  — async TCP probe on known service ports across the local subnet.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import struct
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Literal

import httpx
from config import settings

# ── Module-level constants ────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

FAIL2BAN_SOCK = "/var/run/fail2ban/fail2ban.sock"
PROC_NET_ROUTE = "/proc/net/route"
MAX_SUBNET_HOSTS = 254
TCP_TIMEOUT = 1.0
HTTP_TIMEOUT = 3.0
CONFIRM_TIMEOUT = 2.0

Status = Literal["found", "not_found", "partial", "already_configured"]

# Services to look for during subnet sweep.
# port: TCP port to probe first (fast). path: HTTP path to confirm. url_template: base URL.
KNOWN_SERVICES: list[dict] = [
    {"name": "Prometheus", "port": 9090,  "path": "/-/healthy",                         "env_keys": ["PROMETHEUS_URL"],                              "url_template": "http://{ip}:9090"},
    {"name": "Grafana",    "port": 3000,  "path": "/api/health",                         "env_keys": [],                                              "url_template": "http://{ip}:3000"},
    {"name": "Loki",       "port": 3100,  "path": "/ready",                              "env_keys": ["LOKI_URL"],                                    "url_template": "http://{ip}:3100"},
    {"name": "Portainer",  "port": 9443,  "path": "/api/status",                         "env_keys": [],                                              "url_template": "https://{ip}:9443"},
    {"name": "Proxmox",    "port": 8006,  "path": "/api2/json/version",                  "env_keys": ["PVE1_URL", "PVE1_TOKEN"],                      "url_template": "https://{ip}:8006"},
    {"name": "Graylog",    "port": 9000,  "path": "/api/",                               "env_keys": [],                                              "url_template": "http://{ip}:9000"},
    {"name": "CrowdSec",   "port": 8080,  "path": "/v1/decisions",                       "env_keys": ["CROWDSEC_URL", "CROWDSEC_API_KEY"],             "url_template": "http://{ip}:8080"},
    {"name": "Wazuh",      "port": 55000, "path": "/",                                   "env_keys": [],                                              "url_template": "https://{ip}:55000"},
    {"name": "ntopng",     "port": 3000,  "path": "/lua/rest/v2/get/ntopng/info.lua",    "env_keys": [],                                              "url_template": "http://{ip}:3000"},
    {"name": "FritzBox",   "port": 49000, "path": "/",                                   "env_keys": ["FRITZ_URL"],                                   "url_template": "http://{ip}:49000"},
    {"name": "UniFi",      "port": 443,   "path": "/api/auth/login",                     "env_keys": ["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"],"url_template": "https://{ip}"},
    {"name": "OPNsense",   "port": 443,   "path": "/api/core/firmware/status",           "env_keys": [],                                              "url_template": "https://{ip}"},
    {"name": "Aruba",      "port": 4343,  "path": "/rest/login",                         "env_keys": [],                                              "url_template": "https://{ip}:4343"},
]

# Port → list of services for that port (built once at import time).
PORT_SERVICE_MAP: dict[int, list[dict]] = {}
for _svc in KNOWN_SERVICES:
    PORT_SERVICE_MAP.setdefault(_svc["port"], []).append(_svc)

# Static config audit table — (name, flag, values, env_keys, description).
# fail2ban is socket-checked separately; all others use env var presence.
CONFIG_CHECKS: list[tuple[str, bool, list[str], list[str], str]] = [
    ("CrowdSec",    settings.enable_crowdsec,    [settings.crowdsec_url, settings.crowdsec_api_key],       ["CROWDSEC_URL", "CROWDSEC_API_KEY"],           "Threat intelligence and ban tracking"),
    ("UniFi",       settings.enable_unifi,       [settings.unifi_url, settings.unifi_username, settings.unifi_password], ["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"], "Network health, AP status, client monitoring"),
    ("Proxmox",     settings.enable_proxmox,     [settings.pve1_url, settings.pve1_token],                ["PVE1_URL", "PVE1_TOKEN"],                     "Hypervisor and VM inventory"),
    ("Loki",        settings.enable_loki,        [settings.loki_url],                                     ["LOKI_URL"],                                   "Log aggregation — UniFi events and Traefik logs"),
    ("Prometheus",  settings.enable_prometheus,  [settings.prometheus_url],                               ["PROMETHEUS_URL"],                             "Metrics — ban timeline and event rate charts"),
    ("OpenAI",      settings.enable_openai,      [settings.openai_api_key],                               ["OPENAI_API_KEY"],                             "AI assistant for security questions"),
    ("Workstations",settings.enable_workstations,[settings.workstation_agent_key],                        ["WORKSTATION_AGENT_KEY"],                      "Endpoint monitoring agents (Windows/Linux/macOS)"),
]


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class DiscoveryResult:
    name: str
    status: Status
    detail: str = ""
    ip: str = ""
    port: int = 0
    env_keys: list[str] = field(default_factory=list)
    suggested_values: dict[str, str] = field(default_factory=dict)
    setup_hint: str = ""
    category: str = ""


# ── Network helpers ───────────────────────────────────────────────────────────

def _get_default_gateway() -> str | None:
    try:
        with open(PROC_NET_ROUTE) as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    return socket.inet_ntoa(struct.pack("<I", int(parts[2], 16)))
    except Exception:
        pass
    return None


def _get_local_subnet() -> str | None:
    try:
        import netifaces  # type: ignore
        for iface in netifaces.interfaces():
            for a in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                ip, mask = a.get("addr", ""), a.get("netmask", "")
                if ip and not ip.startswith("127.") and mask:
                    return str(ipaddress.IPv4Network(f"{ip}/{mask}", strict=False))
    except ImportError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            return str(ipaddress.IPv4Network(f"{ip}/24", strict=False))
    except Exception:
        pass
    return None


async def _tcp_open(ip: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=TCP_TIMEOUT)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _http_get(url: str, timeout: float = HTTP_TIMEOUT) -> tuple[int, str]:
    try:
        async with httpx.AsyncClient(verify=False, timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url)
            return r.status_code, r.text[:500]
    except Exception as e:
        return 0, str(e)


# ── Gateway probe functions ───────────────────────────────────────────────────

async def _probe_fritzbox(ip: str, port: int, *, tls: bool = False) -> DiscoveryResult | None:
    scheme = "https" if tls else "http"
    status, body = await _http_get(f"{scheme}://{ip}:{port}/")
    body_lower = body.lower()
    if status > 0 and ("fritz" in body_lower or "avm" in body_lower or "TR-064" in body):
        label = "FritzBox (TLS)" if tls else "FritzBox"
        return DiscoveryResult(
            name=label, status="found", ip=ip, port=port,
            detail=f"AVM FritzBox detected via {'TLS ' if tls else ''}TR-064 endpoint",
            env_keys=["FRITZ_URL", "FRITZ_USER", "FRITZ_PASSWORD"],
            suggested_values={"FRITZ_URL": f"{scheme}://{ip}:{port}"},
            setup_hint="Enable TR-064 in FritzBox UI: Home Network > Network > Allow access for applications",
            category="gateway",
        )
    return None


async def _probe_unifi(ip: str, port: int) -> DiscoveryResult | None:
    status, _ = await _http_get(f"https://{ip}:{port}/api/auth/login")
    if status in (200, 400, 401, 422):
        return DiscoveryResult(
            name="UniFi Controller", status="found", ip=ip, port=port,
            detail="UniFi Network controller API detected",
            env_keys=["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"],
            suggested_values={"UNIFI_URL": f"https://{ip}"},
            setup_hint="Create a local-only admin account — cloud/SSO accounts return HTTP 499.",
            category="gateway",
        )
    return None


async def _probe_pfsense(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_get(f"https://{ip}:{port}/")
    if status > 0 and ("pfsense" in body.lower() or "pfSense" in body):
        return DiscoveryResult(
            name="pfSense", status="found", ip=ip, port=port,
            detail="pfSense firewall detected",
            env_keys=[],
            setup_hint="pfSense REST API available via the pfSense-API package.",
            category="gateway",
        )
    return None


async def _probe_opnsense(ip: str, port: int) -> DiscoveryResult | None:
    status, _ = await _http_get(f"https://{ip}:{port}/api/core/firmware/status")
    if status in (200, 401, 403):
        return DiscoveryResult(
            name="OPNsense", status="found", ip=ip, port=port,
            detail="OPNsense firewall REST API detected",
            env_keys=[],
            setup_hint="Create an API key under System > Access > Users.",
            category="gateway",
        )
    return None


async def _probe_proxmox(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_get(f"https://{ip}:{port}/api2/json/version")
    if status == 200 and "version" in body:
        return DiscoveryResult(
            name="Proxmox VE", status="found", ip=ip, port=port,
            detail="Proxmox VE API detected",
            env_keys=["PVE1_URL", "PVE1_TOKEN"],
            suggested_values={"PVE1_URL": f"https://{ip}:8006"},
            setup_hint="Create an API token: Datacenter > Permissions > API Tokens. Format: user@pam!tokenid=secret",
            category="gateway",
        )
    return None


async def _probe_aruba(ip: str, port: int) -> DiscoveryResult | None:
    status, _ = await _http_get(f"https://{ip}:{port}/rest/login")
    if status in (200, 400, 401):
        return DiscoveryResult(
            name="Aruba Controller", status="found", ip=ip, port=port,
            detail="Aruba network controller REST API detected",
            env_keys=[],
            setup_hint="Enable REST API under Management > REST API Access.",
            category="gateway",
        )
    return None


# Probe table: (port, coroutine_function). Built once at module load.
GatewayProbe = tuple[int, Callable[..., asyncio.coroutines._CoroutineType]]  # type: ignore[type-arg]
GATEWAY_PROBES: list[tuple[int, Callable]] = [
    (49000, _probe_fritzbox),
    (49443, lambda ip, port: _probe_fritzbox(ip, port, tls=True)),
    (443,   _probe_unifi),
    (443,   _probe_pfsense),
    (443,   _probe_opnsense),
    (8006,  _probe_proxmox),
    (4343,  _probe_aruba),
]


# ── Scan layers ───────────────────────────────────────────────────────────────

def _audit_config() -> list[DiscoveryResult]:
    results: list[DiscoveryResult] = []

    sock_present = os.path.exists(FAIL2BAN_SOCK)
    results.append(DiscoveryResult(
        name="fail2ban",
        status="found" if sock_present else "not_found",
        detail="fail2ban socket mounted and accessible" if sock_present else "Socket not mounted",
        setup_hint=(
            "fail2ban available — jail status and ban counts readable via socket."
            if sock_present else
            "To enable: add '- /var/run/fail2ban/fail2ban.sock:/var/run/fail2ban/fail2ban.sock' to docker-compose volumes."
        ),
        category="local",
    ))

    for name, enabled, values, keys, desc in CONFIG_CHECKS:
        configured = bool(values) and all(bool(v) for v in values)
        if not enabled:
            status: Status = "not_found"
            detail = f"Disabled in config (ENABLE_{name.upper()}=false)"
        elif configured:
            status = "already_configured"
            detail = f"{name} is configured and enabled"
        else:
            status = "not_found"
            detail = f"Not configured — {desc}"
        results.append(DiscoveryResult(name=name, status=status, detail=detail, env_keys=keys, category="config"))

    return results


async def _scan_gateway(gateway_ip: str) -> list[DiscoveryResult]:
    tasks = [fn(gateway_ip, port) for port, fn in GATEWAY_PROBES]
    hits = await asyncio.gather(*tasks, return_exceptions=True)
    seen: set[str] = set()
    results: list[DiscoveryResult] = []
    for h in hits:
        if isinstance(h, DiscoveryResult) and h.name not in seen:
            results.append(h)
            seen.add(h.name)
    return results


async def _sweep_subnet(subnet: str) -> list[DiscoveryResult]:
    try:
        hosts = list(ipaddress.IPv4Network(subnet, strict=False).hosts())[:MAX_SUBNET_HOSTS]
    except ValueError:
        return []

    tasks = [
        _tcp_open(str(h), port)
        for h in hosts
        for port in PORT_SERVICE_MAP
    ]
    logger.info("Sweeping %d hosts × %d ports = %d probes", len(hosts), len(PORT_SERVICE_MAP), len(tasks))
    open_flags = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[DiscoveryResult] = []
    seen: set[tuple[str, str]] = set()
    idx = 0

    for h in hosts:
        ip_str = str(h)
        for port, svcs in PORT_SERVICE_MAP.items():
            is_open = open_flags[idx]
            idx += 1
            if not isinstance(is_open, bool) or not is_open:
                continue
            for svc in svcs:
                key = (ip_str, svc["name"])
                if key in seen:
                    continue
                seen.add(key)
                url = svc["url_template"].format(ip=ip_str)
                status, _ = await _http_get(url.rstrip("/") + svc["path"], timeout=CONFIRM_TIMEOUT)
                if status > 0:
                    suggested = {k: url for k in svc["env_keys"] if "URL" in k}
                    results.append(DiscoveryResult(
                        name=svc["name"], status="found", ip=ip_str, port=port,
                        detail=f"Detected at {ip_str}:{port} (HTTP {status})",
                        env_keys=svc["env_keys"],
                        suggested_values=suggested,
                        setup_hint=f"Found {svc['name']} at {url}",
                        category="network",
                    ))

    return results


# ── Public entry point ────────────────────────────────────────────────────────

async def run_scan(include_subnet: bool = True) -> dict:
    started = time.time()
    logger.info("Environment scan started")

    config_results = _audit_config()

    gateway_ip = _get_default_gateway()
    gateway_results = await _scan_gateway(gateway_ip) if gateway_ip else []

    subnet_results: list[DiscoveryResult] = []
    if include_subnet:
        subnet = _get_local_subnet()
        if subnet:
            logger.info("Sweeping subnet %s", subnet)
            subnet_results = await _sweep_subnet(subnet)

    duration = round(time.time() - started, 1)
    logger.info("Environment scan complete in %ss", duration)

    return {
        "config":                [asdict(r) for r in config_results],
        "gateway":               [asdict(r) for r in gateway_results],
        "network":               [asdict(r) for r in subnet_results],
        "gateway_ip":            gateway_ip,
        "scan_duration_seconds": duration,
        "scanned_at":            time.time(),
    }
