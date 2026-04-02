#!/usr/bin/env python3
"""Create and seed secnet.db with PLACEHOLDER data.

Copy this to init-db.py and fill in real IPs/hostnames before running.
"""

import json
import os
import sqlite3
import sys

DB_PATH = os.environ.get("SECNET_DB", "/data/secnet.db")


def main():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.executescript("""
        DROP TABLE IF EXISTS hosts;
        DROP TABLE IF EXISTS known_ips;

        CREATE TABLE hosts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            ip          TEXT NOT NULL,
            group_name  TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT '',
            check_port  INTEGER NOT NULL DEFAULT 22,
            services    TEXT NOT NULL DEFAULT '[]',
            link        TEXT,
            skip_check  INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE known_ips (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname TEXT NOT NULL UNIQUE,
            ip       TEXT NOT NULL DEFAULT ''
        );
    """)

    # ── Host Registry (placeholder data) ─────────────────────────────────────
    hosts = [
        ("Gateway",       "192.168.X.1",   "Core",  "Gateway / Firewall",       443,  '["Firewall"]', None, 0),
        ("DNS-Primary",   "192.168.X.51",  "Core",  "DNS primary",              53,   '["DNS :53"]', None, 0),
        ("DNS-Secondary", "192.168.X.52",  "Core",  "DNS secondary",            53,   '["DNS :53"]', None, 0),
        ("NAS",           "192.168.X.50",  "Nodes", "Storage / Docker host",    22,   '["SSH"]', None, 0),
        ("Hypervisor",    "192.168.X.20",  "Nodes", "Proxmox hypervisor",       8006, '["Proxmox :8006"]', None, 0),
        ("Builder",       "192.168.X.100", "Tools", "Build host",               22,   '["SSH"]', None, 0),
        ("Workstation",   "192.168.X.10",  "Workstations", "Dev workstation",   22,   '["SSH"]', None, 0),
    ]
    cur.executemany(
        "INSERT INTO hosts (name, ip, group_name, role, check_port, services, link, skip_check) VALUES (?,?,?,?,?,?,?,?)",
        hosts,
    )

    # ── Known IPs (placeholder data) ─────────────────────────────────────────
    known_ips = [
        ("vm-web",      "192.168.X.101"),
        ("vm-db",       "192.168.X.102"),
        ("vm-staging",  "192.168.X.103"),
        ("ct-dns",      "192.168.X.104"),
        ("ct-monitor",  "192.168.X.105"),
    ]
    cur.executemany(
        "INSERT INTO known_ips (hostname, ip) VALUES (?,?)",
        known_ips,
    )

    conn.commit()
    conn.close()
    print(f"Database created at {DB_PATH}")
    print(f"  hosts:     {len(hosts)} rows")
    print(f"  known_ips: {len(known_ips)} rows")


if __name__ == "__main__":
    main()
