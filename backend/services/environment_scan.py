"""Environment discovery — three-layer scan to detect integrations the user may want to add.

Layer 1: Config audit — what's configured vs missing in current settings.
Layer 2: Gateway probing — detect FritzBox, UniFi, pfSense, Proxmox at the gateway IP.
Layer 3: Subnet sweep — async TCP probe on known service ports across the local subnet.
"""
from __future__ import annotations
import asyncio
import ipaddress
import logging
import socket
import struct
import time
from dataclasses import dataclass, field, asdict
from typing import Literal

import httpx
from config import settings

logger = logging.getLogger(__name__)

Status = Literal["found", "not_found", "partial", "already_configured"]

KNOWN_SERVICES = [
    {"name": "Prometheus",  "port": 9090, "path": "/-/healthy",        "env_keys": ["PROMETHEUS_URL"],             "url_template": "http://{ip}:9090"},
    {"name": "Grafana",     "port": 3000, "path": "/api/health",        "env_keys": [],                             "url_template": "http://{ip}:3000"},
    {"name": "Loki",        "port": 3100, "path": "/ready",             "env_keys": ["LOKI_URL"],                   "url_template": "http://{ip}:3100"},
    {"name": "Portainer",   "port": 9443, "path": "/api/status",        "env_keys": [],                             "url_template": "https://{ip}:9443"},
    {"name": "Proxmox",     "port": 8006, "path": "/api2/json/version", "env_keys": ["PVE1_URL", "PVE1_TOKEN"],     "url_template": "https://{ip}:8006"},
    {"name": "Graylog",     "port": 9000, "path": "/api/",              "env_keys": [],                             "url_template": "http://{ip}:9000"},
    {"name": "Zabbix",      "port": 8080, "path": "/zabbix/",           "env_keys": [],                             "url_template": "http://{ip}:8080"},
    {"name": "CrowdSec",    "port": 8080, "path": "/v1/decisions",      "env_keys": ["CROWDSEC_URL","CROWDSEC_API_KEY"], "url_template": "http://{ip}:8080"},
    {"name": "Wazuh",       "port": 55000,"path": "/",                  "env_keys": [],                             "url_template": "https://{ip}:55000"},
    {"name": "ntopng",      "port": 3000, "path": "/lua/rest/v2/get/ntopng/info.lua", "env_keys": [],              "url_template": "http://{ip}:3000"},
    {"name": "FritzBox",    "port": 49000,"path": "/",                  "env_keys": ["FRITZ_URL"],                  "url_template": "http://{ip}:49000"},
    {"name": "UniFi",       "port": 443,  "path": "/api/auth/login",    "env_keys": ["UNIFI_URL","UNIFI_USERNAME","UNIFI_PASSWORD"], "url_template": "https://{ip}"},
    {"name": "OPNsense",    "port": 443,  "path": "/api/core/firmware/status", "env_keys": [],                     "url_template": "https://{ip}"},
    {"name": "Aruba",       "port": 4343, "path": "/rest/login",        "env_keys": [],                             "url_template": "https://{ip}:4343"},
]

GATEWAY_SERVICES = [
    {"name": "FritzBox",    "port": 49000, "probe": "_probe_fritzbox"},
    {"name": "FritzBox",    "port": 49443, "probe": "_probe_fritzbox_tls"},
    {"name": "UniFi",       "port": 443,   "probe": "_probe_unifi"},
    {"name": "pfSense",     "port": 443,   "probe": "_probe_pfsense"},
    {"name": "OPNsense",    "port": 443,   "probe": "_probe_opnsense"},
    {"name": "Proxmox",     "port": 8006,  "probe": "_probe_proxmox"},
    {"name": "Aruba",       "port": 4343,  "probe": "_probe_aruba"},
]


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


def _get_default_gateway() -> str | None:
    """Read default gateway from /proc/net/route."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    gw_hex = parts[2]
                    gw_int = int(gw_hex, 16)
                    return socket.inet_ntoa(struct.pack("<I", gw_int))
    except Exception:
        pass
    return None


def _get_local_subnet() -> str | None:
    """Get the container's primary non-loopback subnet (e.g. 192.168.1.0/24)."""
    try:
        import netifaces  # type: ignore
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [])
            for a in addrs:
                ip = a.get("addr", "")
                mask = a.get("netmask", "")
                if ip and not ip.startswith("127.") and mask:
                    net = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
                    return str(net)
    except ImportError:
        pass
    # Fallback: use socket to find our IP, assume /24
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


async def _tcp_open(ip: str, port: int, timeout: float = 1.5) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _http_probe(url: str, timeout: float = 3.0, verify: bool = False) -> tuple[int, str]:
    try:
        async with httpx.AsyncClient(verify=verify, timeout=timeout, follow_redirects=True) as c:
            r = await c.get(url)
            return r.status_code, r.text[:500]
    except Exception as e:
        return 0, str(e)


async def _probe_fritzbox(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"http://{ip}:{port}/", timeout=3.0)
    if status > 0 and ("fritz" in body.lower() or "avm" in body.lower() or "TR-064" in body):
        return DiscoveryResult(
            name="FritzBox", status="found", ip=ip, port=port,
            detail="AVM FritzBox detected via TR-064 endpoint",
            env_keys=["FRITZ_URL", "FRITZ_USER", "FRITZ_PASSWORD"],
            suggested_values={"FRITZ_URL": f"http://{ip}:{port}"},
            setup_hint="FritzBox TR-064 API — enable in FritzBox UI under Home Network > Network > Allow access for applications",
            category="gateway",
        )
    return None


async def _probe_fritzbox_tls(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/", timeout=3.0, verify=False)
    if status > 0 and ("fritz" in body.lower() or "avm" in body.lower()):
        return DiscoveryResult(
            name="FritzBox (TLS)", status="found", ip=ip, port=port,
            detail="AVM FritzBox detected via TLS TR-064 endpoint",
            env_keys=["FRITZ_URL", "FRITZ_USER", "FRITZ_PASSWORD"],
            suggested_values={"FRITZ_URL": f"https://{ip}:{port}"},
            setup_hint="FritzBox TR-064 over TLS. Use your FritzBox admin credentials.",
            category="gateway",
        )
    return None


async def _probe_unifi(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/api/auth/login", timeout=3.0, verify=False)
    if status in (200, 400, 401, 422):
        return DiscoveryResult(
            name="UniFi Controller", status="found", ip=ip, port=port,
            detail="UniFi Network controller API detected",
            env_keys=["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"],
            suggested_values={"UNIFI_URL": f"https://{ip}"},
            setup_hint="Create a local-only admin account in UniFi — cloud/SSO accounts return HTTP 499.",
            category="gateway",
        )
    return None


async def _probe_pfsense(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/", timeout=3.0, verify=False)
    if status > 0 and ("pfsense" in body.lower() or "pfSense" in body):
        return DiscoveryResult(
            name="pfSense", status="found", ip=ip, port=port,
            detail="pfSense firewall detected",
            env_keys=[],
            setup_hint="pfSense REST API available via the API package. Consider installing it for firewall rule visibility.",
            category="gateway",
        )
    return None


async def _probe_opnsense(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/api/core/firmware/status", timeout=3.0, verify=False)
    if status in (200, 401, 403):
        return DiscoveryResult(
            name="OPNsense", status="found", ip=ip, port=port,
            detail="OPNsense firewall REST API detected",
            env_keys=[],
            setup_hint="OPNsense has a built-in REST API. Create an API key under System > Access > Users.",
            category="gateway",
        )
    return None


async def _probe_proxmox(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/api2/json/version", timeout=3.0, verify=False)
    if status == 200 and "version" in body:
        return DiscoveryResult(
            name="Proxmox VE", status="found", ip=ip, port=port,
            detail="Proxmox VE API detected at gateway",
            env_keys=["PVE1_URL", "PVE1_TOKEN"],
            suggested_values={"PVE1_URL": f"https://{ip}:8006"},
            setup_hint="Create a Proxmox API token: Datacenter > Permissions > API Tokens. Format: user@pam!tokenid=secret",
            category="gateway",
        )
    return None


async def _probe_aruba(ip: str, port: int) -> DiscoveryResult | None:
    status, body = await _http_probe(f"https://{ip}:{port}/rest/login", timeout=3.0, verify=False)
    if status in (200, 400, 401):
        return DiscoveryResult(
            name="Aruba Controller", status="found", ip=ip, port=port,
            detail="Aruba network controller REST API detected",
            env_keys=[],
            setup_hint="Aruba AOS REST API available. Enable under Management > REST API Access.",
            category="gateway",
        )
    return None


def _audit_current_config() -> list[DiscoveryResult]:
    """Report what's already configured vs missing."""
    results = []
    checks = [
        ("CrowdSec", settings.enable_crowdsec, [settings.crowdsec_url, settings.crowdsec_api_key],
         ["CROWDSEC_URL", "CROWDSEC_API_KEY"], "Threat intelligence and ban tracking"),
        ("UniFi", settings.enable_unifi, [settings.unifi_url, settings.unifi_username, settings.unifi_password],
         ["UNIFI_URL", "UNIFI_USERNAME", "UNIFI_PASSWORD"], "Network health, AP status, client monitoring"),
        ("Proxmox", settings.enable_proxmox, [settings.pve1_url, settings.pve1_token],
         ["PVE1_URL", "PVE1_TOKEN"], "Hypervisor and VM inventory"),
        ("Loki", settings.enable_loki, [settings.loki_url],
         ["LOKI_URL"], "Log aggregation — UniFi events and Traefik logs"),
        ("Prometheus", settings.enable_prometheus, [settings.prometheus_url],
         ["PROMETHEUS_URL"], "Metrics — ban timeline and event rate charts"),
        ("OpenAI", settings.enable_openai, [settings.openai_api_key],
         ["OPENAI_API_KEY"], "AI assistant for security questions"),
        ("Workstations", settings.enable_workstations, [settings.workstation_agent_key],
         ["WORKSTATION_AGENT_KEY"], "Endpoint monitoring agents (Windows/Linux/macOS)"),
        ("fail2ban", True, [],  # socket-based, not env configured
         [], "Local intrusion prevention — ban counts and jail status"),
    ]

    for name, enabled, values, keys, desc in checks:
        if name == "fail2ban":
            import os
            sock = "/var/run/fail2ban/fail2ban.sock"
            if os.path.exists(sock):
                results.append(DiscoveryResult(
                    name="fail2ban", status="found",
                    detail="fail2ban socket mounted and accessible",
                    setup_hint="fail2ban is available. Future integration can read jail status and ban counts directly.",
                    category="local",
                ))
            else:
                results.append(DiscoveryResult(
                    name="fail2ban", status="not_found",
                    detail="Socket not mounted — add volume to docker-compose.yml",
                    setup_hint="To enable: add '- /var/run/fail2ban/fail2ban.sock:/var/run/fail2ban/fail2ban.sock' to your volumes.",
                    category="local",
                ))
            continue

        configured = all(bool(v) for v in values) if values else False
        if not enabled:
            status: Status = "not_found"
            detail = f"Disabled in config (ENABLE_{name.upper()}=false)"
        elif configured:
            status = "already_configured"
            detail = f"{name} is configured and enabled"
        else:
            status = "not_found"
            detail = f"Not configured — {desc}"

        results.append(DiscoveryResult(
            name=name, status=status, detail=detail,
            env_keys=keys, category="config",
        ))

    return results


async def _scan_gateway(gateway_ip: str) -> list[DiscoveryResult]:
    results = []
    probe_map = {
        "_probe_fritzbox": _probe_fritzbox,
        "_probe_fritzbox_tls": _probe_fritzbox_tls,
        "_probe_unifi": _probe_unifi,
        "_probe_pfsense": _probe_pfsense,
        "_probe_opnsense": _probe_opnsense,
        "_probe_proxmox": _probe_proxmox,
        "_probe_aruba": _probe_aruba,
    }
    tasks = []
    for svc in GATEWAY_SERVICES:
        fn = probe_map.get(svc["probe"])
        if fn:
            tasks.append(fn(gateway_ip, svc["port"]))
    hits = await asyncio.gather(*tasks, return_exceptions=True)
    seen = set()
    for h in hits:
        if isinstance(h, DiscoveryResult) and h.name not in seen:
            results.append(h)
            seen.add(h.name)
    return results


async def _sweep_subnet(subnet: str) -> list[DiscoveryResult]:
    """Async TCP sweep of known service ports across the subnet."""
    try:
        net = ipaddress.IPv4Network(subnet, strict=False)
    except ValueError:
        return []

    # Limit to /24 max (256 hosts)
    hosts = list(net.hosts())
    if len(hosts) > 254:
        hosts = hosts[:254]

    # Unique ports to check
    port_to_services: dict[int, list[dict]] = {}
    for svc in KNOWN_SERVICES:
        port_to_services.setdefault(svc["port"], []).append(svc)

    # Build probe tasks
    async def probe_host_port(ip_str: str, port: int) -> tuple[str, int, bool]:
        open_ = await _tcp_open(ip_str, port, timeout=1.0)
        return ip_str, port, open_

    tasks = [
        probe_host_port(str(h), port)
        for h in hosts
        for port in port_to_services
    ]

    logger.info(f"Sweeping {len(hosts)} hosts × {len(port_to_services)} ports = {len(tasks)} probes")
    raw = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[DiscoveryResult] = []
    seen: set[tuple[str, str]] = set()

    for item in raw:
        if isinstance(item, Exception) or not item[2]:
            continue
        ip_str, port, _ = item
        for svc in port_to_services.get(port, []):
            key = (ip_str, svc["name"])
            if key in seen:
                continue
            seen.add(key)

            # Quick HTTP confirm
            url = svc["url_template"].format(ip=ip_str)
            path_url = url.rstrip("/") + svc.get("path", "/")
            status, body = await _http_probe(path_url, timeout=2.0, verify=False)

            if status > 0:
                suggested = {}
                for k in svc["env_keys"]:
                    if "URL" in k:
                        suggested[k] = url
                results.append(DiscoveryResult(
                    name=svc["name"], status="found",
                    ip=ip_str, port=port,
                    detail=f"Detected at {ip_str}:{port} (HTTP {status})",
                    env_keys=svc["env_keys"],
                    suggested_values=suggested,
                    setup_hint=f"Found {svc['name']} at {url}",
                    category="network",
                ))

    return results


async def run_scan(include_subnet: bool = True) -> dict:
    """Run all three layers. Returns structured JSON-serializable dict."""
    started = time.time()
    logger.info("Environment scan started")

    config_results = _audit_current_config()

    gateway_ip = _get_default_gateway()
    gateway_results: list[DiscoveryResult] = []
    if gateway_ip:
        logger.info(f"Probing gateway {gateway_ip}")
        gateway_results = await _scan_gateway(gateway_ip)

    subnet_results: list[DiscoveryResult] = []
    if include_subnet:
        subnet = _get_local_subnet()
        if subnet:
            logger.info(f"Sweeping subnet {subnet}")
            subnet_results = await _sweep_subnet(subnet)

    duration = round(time.time() - started, 1)
    logger.info(f"Environment scan complete in {duration}s")

    return {
        "config": [asdict(r) for r in config_results],
        "gateway": [asdict(r) for r in gateway_results],
        "network": [asdict(r) for r in subnet_results],
        "gateway_ip": gateway_ip,
        "scan_duration_seconds": duration,
        "scanned_at": time.time(),
    }
