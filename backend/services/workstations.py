"""Workstation registry — read/write from SQLite."""
from __future__ import annotations
import json
import time
import db

SUSPICIOUS_NAMES = {
    'mimikatz.exe', 'wce.exe', 'fgdump.exe', 'procdump.exe',
    'tor.exe', 'torsvc.exe', 'nc.exe', 'ncat.exe', 'netcat.exe',
    'psexec.exe', 'psexecsvc.exe', 'wermgr.exe',
}
RECON_NAMES = {'net.exe', 'nltest.exe', 'whoami.exe', 'nslookup.exe', 'arp.exe'}
NETWORK_NAMES = {'mstsc.exe', 'ssh.exe', 'putty.exe', 'winscp.exe'}
HIGH_CPU_LSASS = 25  # lsass.exe above this % is suspicious


def _compute_flags(name: str, cpu: float) -> list[str]:
    n = name.lower()
    if n in SUSPICIOUS_NAMES:
        return ['suspicious', 'network'] if n in {'tor.exe', 'torsvc.exe', 'nc.exe', 'ncat.exe', 'netcat.exe'} else ['suspicious']
    if n == 'lsass.exe' and cpu > HIGH_CPU_LSASS:
        return ['critical', 'suspicious']
    if n == 'rundll32.exe' and cpu > 15:
        return ['suspicious', 'injection']
    if n in RECON_NAMES:
        return ['suspicious', 'recon']
    if n in NETWORK_NAMES:
        return ['network']
    return []


def _compute_status(procs: list[dict]) -> tuple[str, list[str]]:
    alerts = []
    worst = 'healthy'
    for p in procs:
        flags = p.get('flags', [])
        if 'critical' in flags or 'injection' in flags:
            worst = 'compromised'
            alerts.append(f"{p['name']} — {', '.join(flags)}")
        elif 'suspicious' in flags and worst != 'compromised':
            worst = 'suspicious'
            alerts.append(f"{p['name']} — {', '.join(flags)}")
    return worst, alerts


def upsert_workstation(data: dict) -> None:
    hostname = data['hostname']
    procs_raw = data.get('processes', [])

    # Compute flags server-side
    procs = []
    for p in procs_raw:
        flags = _compute_flags(p.get('name', ''), p.get('cpu', 0))
        procs.append({**p, 'flags': flags})

    status, alerts = _compute_status(procs)

    conn = db.connect()
    try:
        conn.execute("""
            INSERT INTO workstations (id, hostname, ip, mac, os, domain, ws_user,
                session_start, cpu, ram, disk, status, alerts, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                ip=excluded.ip, mac=excluded.mac, os=excluded.os,
                domain=excluded.domain, ws_user=excluded.ws_user,
                session_start=excluded.session_start,
                cpu=excluded.cpu, ram=excluded.ram, disk=excluded.disk,
                status=excluded.status, alerts=excluded.alerts,
                last_seen=excluded.last_seen
        """, (
            hostname, hostname,
            data.get('ip', ''), data.get('mac', ''),
            data.get('os', ''), data.get('domain', ''),
            data.get('user', ''),
            data.get('session_start', int(time.time())),
            int(data.get('cpu', 0)), int(data.get('ram', 0)), int(data.get('disk', 0)),
            status, json.dumps(alerts), int(time.time()),
        ))

        conn.execute("DELETE FROM workstation_processes WHERE ws_id = ?", (hostname,))
        for p in procs:
            conn.execute(
                "INSERT INTO workstation_processes (ws_id, name, pid, cpu, ram, flags) VALUES (?,?,?,?,?,?)",
                (hostname, p.get('name',''), p.get('pid',0), p.get('cpu',0), p.get('ram',0), json.dumps(p.get('flags',[])))
            )

        events = data.get('events', [])[-50:]
        conn.execute("DELETE FROM workstation_events WHERE ws_id = ?", (hostname,))
        for ev in events:
            conn.execute(
                "INSERT INTO workstation_events (ws_id, event_id, level, ev_time, msg) VALUES (?,?,?,?,?)",
                (hostname, ev.get('id', 0), ev.get('level', 'info'), ev.get('time', ''), ev.get('msg', ''))
            )

        conn.commit()
    finally:
        conn.close()


def get_all() -> list[dict]:
    conn = db.connect()
    try:
        ws_rows = conn.execute("SELECT * FROM workstations ORDER BY last_seen DESC").fetchall()
        result = []
        for ws in ws_rows:
            ws_id = ws['id']
            procs = conn.execute(
                "SELECT name, pid, cpu, ram, flags FROM workstation_processes WHERE ws_id = ?", (ws_id,)
            ).fetchall()
            events = conn.execute(
                "SELECT event_id, level, ev_time, msg FROM workstation_events WHERE ws_id = ? ORDER BY rowid DESC LIMIT 20", (ws_id,)
            ).fetchall()
            result.append({
                'id': ws_id,
                'hostname': ws['hostname'],
                'ip': ws['ip'],
                'mac': ws['mac'],
                'os': ws['os'],
                'domain': ws['domain'],
                'user': ws['ws_user'],
                'session_start': ws['session_start'],
                'cpu': ws['cpu'],
                'ram': ws['ram'],
                'disk': ws['disk'],
                'status': ws['status'],
                'alerts': json.loads(ws['alerts']),
                'last_seen': ws['last_seen'],
                'processes': [{'name': p['name'], 'pid': p['pid'], 'cpu': p['cpu'], 'ram': p['ram'], 'flags': json.loads(p['flags'])} for p in procs],
                'events': [{'id': e['event_id'], 'level': e['level'], 'time': e['ev_time'], 'msg': e['msg']} for e in events],
            })
        return result
    finally:
        conn.close()
