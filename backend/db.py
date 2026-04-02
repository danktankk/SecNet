"""Shared SQLite access for the security dashboard."""

from __future__ import annotations
import json
import os
import sqlite3
from typing import Any

_DB_PATH = os.environ.get("SECNET_DB", "/data/secnet.db")


_initialized = False


def init_db() -> None:
    """Create tables if they don't exist. Call once at startup."""
    global _initialized
    if _initialized:
        return
    conn = _connect()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS hosts (
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
            CREATE TABLE IF NOT EXISTS known_ips (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                hostname TEXT NOT NULL UNIQUE,
                ip       TEXT NOT NULL DEFAULT ''
            );
        """)

            CREATE TABLE IF NOT EXISTS workstations (
                id           TEXT PRIMARY KEY,
                hostname     TEXT NOT NULL,
                ip           TEXT NOT NULL DEFAULT '',
                mac          TEXT NOT NULL DEFAULT '',
                os           TEXT NOT NULL DEFAULT '',
                domain       TEXT NOT NULL DEFAULT '',
                ws_user      TEXT NOT NULL DEFAULT '',
                session_start INTEGER NOT NULL DEFAULT 0,
                cpu          INTEGER NOT NULL DEFAULT 0,
                ram          INTEGER NOT NULL DEFAULT 0,
                disk         INTEGER NOT NULL DEFAULT 0,
                status       TEXT NOT NULL DEFAULT 'healthy',
                alerts       TEXT NOT NULL DEFAULT '[]',
                last_seen    INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS workstation_processes (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                ws_id TEXT NOT NULL,
                name  TEXT NOT NULL,
                pid   INTEGER NOT NULL,
                cpu   REAL NOT NULL DEFAULT 0,
                ram   INTEGER NOT NULL DEFAULT 0,
                flags TEXT NOT NULL DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS workstation_events (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                ws_id    TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                level    TEXT NOT NULL DEFAULT 'info',
                ev_time  TEXT NOT NULL,
                msg      TEXT NOT NULL
            );
        conn.commit()
    finally:
        conn.close()
    _initialized = True


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_host_registry() -> list[dict[str, Any]]:
    """Return all rows from the hosts table as dicts matching the old HOST_REGISTRY format."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name, ip, group_name, role, check_port, services, link, skip_check FROM hosts"
        ).fetchall()
        result = []
        for r in rows:
            entry: dict[str, Any] = {
                "name": r["name"],
                "ip": r["ip"],
                "group": r["group_name"],
                "role": r["role"],
                "check_port": r["check_port"],
                "services": json.loads(r["services"]),
            }
            if r["link"]:
                entry["link"] = r["link"]
            if r["skip_check"]:
                entry["skip_check"] = True
            result.append(entry)
        return result
    finally:
        conn.close()


def lookup_known_ip(hostname: str) -> str:
    """Look up a hostname in the known_ips table. Returns empty string if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT ip FROM known_ips WHERE hostname = ?", (hostname,)
        ).fetchone()
        return row["ip"] if row else ""
    finally:
        conn.close()
