"""Auto-discovery — populate hosts table from Proxmox on startup.

Runs once at startup. Skips hosts already in the DB (matched by IP).
Adds new discoveries. Never deletes or overwrites existing entries.
"""
from __future__ import annotations
import re
import json
import logging
import sqlite3

import httpx
from config import settings
import db

logger = logging.getLogger(__name__)




def _existing_ips() -> set[str]:
    conn = db.connect()
    try:
        return {r["ip"] for r in conn.execute("SELECT ip FROM hosts").fetchall()}
    finally:
        conn.close()


def _insert_host(name: str, ip: str, group: str, role: str, check_port: int = 22, services: list[str] | None = None, link: str | None = None):
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO hosts (name, ip, group_name, role, check_port, services, link, skip_check) VALUES (?,?,?,?,?,?,?,0)",
            (name, ip, group, role, check_port, json.dumps(services or []), link),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def _insert_known_ip(hostname: str, ip: str):
    conn = db.connect()
    try:
        conn.execute("INSERT OR IGNORE INTO known_ips (hostname, ip) VALUES (?,?)", (hostname, ip))
        conn.commit()
    finally:
        conn.close()


def _discover_proxmox() -> list[dict]:
    """Pull all VMs and LXCs from configured Proxmox nodes."""
    hosts = []
    nodes_config = [
        (settings.pve1_url, settings.pve1_token, "PVE1"),
        (settings.pve2_url, settings.pve2_token, "PVE2"),
        (settings.pve3_url, settings.pve3_token, "PVE3"),
    ]
    for base_url, token, node_label in nodes_config:
        if not base_url or not token:
            continue
        try:
            c = httpx.Client(verify=False, timeout=10)
            headers = {"Authorization": f"PVEAPIToken={token}"}

            # Get node name
            r = c.get(f"{base_url}/api2/json/nodes", headers=headers)
            r.raise_for_status()
            nodes = r.json().get("data", [])
            if not nodes:
                continue
            node_name = nodes[0].get("node", "unknown")

            # Add the PVE node itself
            pve_ip = base_url.replace("https://", "").replace(":8006", "")
            hosts.append({
                "name": node_label, "ip": pve_ip, "group": "Nodes",
                "role": f"Proxmox hypervisor ({node_name})",
                "check_port": 8006, "services": ["Proxmox :8006"],
                "link": base_url,
            })

            # Get VMs
            for endpoint, gtype in [("qemu", "VM"), ("lxc", "LXC")]:
                r = c.get(f"{base_url}/api2/json/nodes/{node_name}/{endpoint}", headers=headers)
                r.raise_for_status()
                for guest in r.json().get("data", []):
                    name = guest.get("name", f"{gtype}-{guest.get('vmid', '?')}")
                    status = guest.get("status", "unknown")
                    ip = ""

                    # Try to get IP for running guests
                    if status == "running":
                        vmid = guest.get("vmid")
                        try:
                            if endpoint == "lxc":
                                cr = c.get(f"{base_url}/api2/json/nodes/{node_name}/lxc/{vmid}/config", headers=headers)
                                if cr.status_code == 200:
                                    cfg = cr.json().get("data", {})
                                    for key in sorted(cfg.keys()):
                                        if key.startswith("net"):
                                            m = re.search(r"ip=(\d+\.\d+\.\d+\.\d+)", cfg[key])
                                            if m:
                                                ip = m.group(1)
                                                break
                            else:
                                cr = c.get(f"{base_url}/api2/json/nodes/{node_name}/qemu/{vmid}/agent/network-get-interfaces", headers=headers)
                                if cr.status_code == 200:
                                    for iface in cr.json().get("data", []):
                                        for addr in iface.get("ip-addresses", []):
                                            a = addr.get("ip-address", "")
                                            if a and not a.startswith("127.") and not a.startswith("fe80") and ":" not in a:
                                                ip = a
                                                break
                                        if ip:
                                            break
                        except Exception:
                            pass

                    if not ip:
                        continue  # skip guests with no IP — can't health-check them

                    hosts.append({
                        "name": name, "ip": ip, "group": "Infrastructure",
                        "role": f"{gtype} on {node_label} ({status})",
                        "check_port": 22, "services": [],
                    })
            c.close()
        except Exception as e:
            logger.warning(f"Proxmox discovery failed for {node_label}: {e}")
    return hosts


def run_discovery():
    """Main entry point — called once at startup."""
    existing = _existing_ips()
    added = 0

    # Proxmox
    if settings.enable_proxmox and (settings.pve1_url or settings.pve2_url or settings.pve3_url):
        for host in _discover_proxmox():
            if host["ip"] not in existing:
                _insert_host(**host)
                _insert_known_ip(host["name"], host["ip"])
                existing.add(host["ip"])
                added += 1
                logger.info(f"Discovered: {host['name']} ({host['ip']}) [{host['group']}]")

    if added:
        logger.info(f"Discovery complete: {added} new hosts added")
    else:
        logger.info(f"Discovery complete: no new hosts (DB has {len(existing)} existing)")
