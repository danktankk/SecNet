"""Proxmox network inventory + nmap port scanning."""

from __future__ import annotations
import asyncio
import ipaddress
import time
import re
from typing import Any
import httpx
from cachetools import TTLCache
from config import settings
from db import lookup_known_ip

_scan_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)

_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(verify=False, timeout=10)
    return _client


async def _pve_get(base_url: str, token: str, path: str) -> Any:
    c = await _get_client()
    r = await c.get(
        f"{base_url}/api2/json{path}",
        headers={"Authorization": f"PVEAPIToken={token}"},
    )
    r.raise_for_status()
    return r.json().get("data", [])


async def _get_node_name(base_url: str, token: str) -> str:
    nodes = await _pve_get(base_url, token, "/nodes")
    if nodes:
        return nodes[0].get("node", "unknown")
    return "unknown"


async def _get_node_inventory(base_url: str, token: str) -> dict:
    node_name = await _get_node_name(base_url, token)
    status_data = await _pve_get(base_url, token, f"/nodes/{node_name}/status")

    cpu_pct = 0
    mem_used = 0
    mem_total = 1
    if isinstance(status_data, dict):
        cpu_pct = round(status_data.get("cpu", 0) * 100, 1)
        mem_used = status_data.get("memory", {}).get("used", 0)
        mem_total = status_data.get("memory", {}).get("total", 1)

    vms_raw, lxcs_raw = await asyncio.gather(
        _pve_get(base_url, token, f"/nodes/{node_name}/qemu"),
        _pve_get(base_url, token, f"/nodes/{node_name}/lxc"),
    )

    async def _get_guest_ip(gtype: str, vmid: int, status: str) -> str:
        """Try to get primary IP for a running guest."""
        if status != "running":
            return ""
        try:
            if gtype == "qemu":
                ifaces = await _pve_get(base_url, token, f"/nodes/{node_name}/qemu/{vmid}/agent/network-get-interfaces")
                for iface in (ifaces or []):
                    for addr in iface.get("ip-addresses", []):
                        ip = addr.get("ip-address", "")
                        if ip and not ip.startswith("127.") and not ip.startswith("fe80") and ":" not in ip:
                            return ip
            else:
                config = await _pve_get(base_url, token, f"/nodes/{node_name}/lxc/{vmid}/config")
                if isinstance(config, dict):
                    for key in sorted(config.keys()):
                        if key.startswith("net"):
                            val = config[key]
                            m = re.search(r"ip=(\d+\.\d+\.\d+\.\d+)", val)
                            if m:
                                return m.group(1)
        except Exception:
            pass
        # Fallback to known IP map
        return ""

    guests = []
    ip_tasks = []
    for vm in (vms_raw or []):
        ip_tasks.append(_get_guest_ip("qemu", vm.get("vmid"), vm.get("status", "")))
        guests.append({
            "type": "qemu",
            "vmid": vm.get("vmid"),
            "name": vm.get("name", ""),
            "status": vm.get("status", "unknown"),
            "cpu": round(vm.get("cpu", 0) * 100, 1) if vm.get("cpu") else 0,
            "mem_used": vm.get("mem", 0),
            "mem_total": vm.get("maxmem", 1),
            "mem_pct": round(vm.get("mem", 0) / max(vm.get("maxmem", 1), 1) * 100, 1),
            "ip": "",
        })
    for ct in (lxcs_raw or []):
        ip_tasks.append(_get_guest_ip("lxc", ct.get("vmid"), ct.get("status", "")))
        guests.append({
            "type": "lxc",
            "vmid": ct.get("vmid"),
            "name": ct.get("name", ""),
            "status": ct.get("status", "unknown"),
            "cpu": round(ct.get("cpu", 0) * 100, 1) if ct.get("cpu") else 0,
            "mem_used": ct.get("mem", 0),
            "mem_total": ct.get("maxmem", 1),
            "mem_pct": round(ct.get("mem", 0) / max(ct.get("maxmem", 1), 1) * 100, 1),
            "ip": "",
        })

    ips = await asyncio.gather(*ip_tasks, return_exceptions=True)
    for i, ip in enumerate(ips):
        if isinstance(ip, str) and ip:
            guests[i]["ip"] = ip
        elif not guests[i]["ip"]:
            # Fallback to known IP map
            guests[i]["ip"] = lookup_known_ip(guests[i]["name"])

    return {
        "node": node_name,
        "url": base_url,
        "cpu_pct": cpu_pct,
        "mem_used": mem_used,
        "mem_total": mem_total,
        "mem_pct": round(mem_used / max(mem_total, 1) * 100, 1),
        "guests": sorted(guests, key=lambda g: g["vmid"]),
    }


async def get_full_inventory() -> list[dict]:
    nodes_config = [
        (settings.pve1_url, settings.pve1_token),
        (settings.pve2_url, settings.pve2_token),
        (settings.pve3_url, settings.pve3_token),
    ]
    results = []
    for url, token in nodes_config:
        if not token:
            continue
        try:
            inv = await _get_node_inventory(url, token)
            results.append(inv)
        except Exception as e:
            # Return error node so frontend knows it failed
            host = url.replace("https://", "").replace(":8006", "")
            results.append({"node": host, "url": url, "error": str(e), "guests": []})
    return results


def _parse_nmap_output(output: str) -> list[dict]:
    """Parse nmap text output into port entries."""
    ports = []
    in_ports = False
    for line in output.splitlines():
        if line.startswith("PORT"):
            in_ports = True
            continue
        if in_ports:
            if not line.strip() or line.startswith("Nmap") or line.startswith("Service"):
                break
            m = re.match(r"(\d+)/(\w+)\s+(\w+)\s+(.*)", line)
            if m:
                port_num = int(m.group(1))
                proto = m.group(2)
                state = m.group(3)
                service = m.group(4).strip()
                # Color classification
                safe_ports = {22, 80, 443, 53, 8006, 8080, 8443}
                danger_ports = {23, 445, 3389, 1433, 3306, 5432, 6379, 27017}
                if port_num in danger_ports:
                    severity = "danger"
                elif port_num in safe_ports:
                    severity = "safe"
                else:
                    severity = "unusual"
                ports.append({
                    "port": port_num,
                    "proto": proto,
                    "state": state,
                    "service": service,
                    "severity": severity,
                })
    return ports


async def scan_host(ip: str, force: bool = False) -> dict:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return {"error": f"Invalid IP address: {ip}"}

    cache_key = f"scan:{ip}"
    if not force and cache_key in _scan_cache:
        return _scan_cache[cache_key]

    try:
        proc = await asyncio.create_subprocess_exec(
            "nmap", "-sT", "-T4", "--top-ports", "1000", ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        output = stdout.decode()
        ports = _parse_nmap_output(output)
        result = {
            "ip": ip,
            "ports": ports,
            "scanned_at": int(time.time()),
            "error": None,
        }
    except asyncio.TimeoutError:
        result = {"ip": ip, "ports": [], "scanned_at": int(time.time()), "error": "Scan timed out"}
    except Exception as e:
        result = {"ip": ip, "ports": [], "scanned_at": int(time.time()), "error": str(e)}

    _scan_cache[cache_key] = result
    return result


async def get_scan_results(ip: str) -> dict | None:
    cache_key = f"scan:{ip}"
    return _scan_cache.get(cache_key)
