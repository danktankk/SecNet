#!/usr/bin/env python3
"""
SecNet Windows Agent
Collects system stats, processes, and event log entries,
then POSTs to the SecNet dashboard every 30 seconds.

Requirements: pip install psutil requests
Optional:     pip install pywin32  (for real Windows event log)

Usage: python secnet-agent.py --url http://192.168.160.169:8088 --key YOUR_AGENT_KEY
"""
import argparse
import json
import platform
import socket
import time
import subprocess
import logging

import psutil
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('secnet-agent')

INTERVAL = 30
MAX_PROCS = 40
MAX_EVENTS = 30
SECURITY_EVENT_IDS = {4624, 4625, 4648, 4688, 4703, 4704, 4776, 4800, 4801, 5156, 7045}


def get_primary_ip_mac():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = '127.0.0.1'
    mac = ''
    for iface, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.address == ip:
                for a2 in addrs:
                    if a2.family == psutil.AF_LINK:
                        mac = a2.address
                break
    return ip, mac


def get_logged_in_user():
    try:
        users = psutil.users()
        if users:
            return users[0].name, int(users[0].started)
    except Exception:
        pass
    import os
    return os.environ.get('USERNAME', 'unknown'), int(time.time())


def get_processes():
    procs = []
    for p in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_info']):
        try:
            info = p.info
            ram_mb = int((info['memory_info'].rss if info['memory_info'] else 0) / 1024 / 1024)
            procs.append({'name': info['name'] or '', 'pid': info['pid'], 'cpu': round(info['cpu_percent'] or 0, 1), 'ram': ram_mb})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:MAX_PROCS]


def get_events_powershell():
    ids = ','.join(str(i) for i in SECURITY_EVENT_IDS)
    ps = f"Get-WinEvent -LogName Security -MaxEvents 100 | Where-Object {{$_.Id -in @({ids})}} | Select-Object -First {MAX_EVENTS} Id,TimeCreated,Message | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell', '-NonInteractive', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=15)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        raw = json.loads(result.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        events = []
        for ev in raw:
            eid = ev.get('Id', 0)
            ts = ev.get('TimeCreated', {})
            ts_str = ts.get('value', ts.get('Value', '')) if isinstance(ts, dict) else str(ts)
            try:
                dt = time.strptime(ts_str[:19], '%Y-%m-%dT%H:%M:%S')
                t = time.strftime('%H:%M:%S', dt)
            except Exception:
                t = ts_str[:8] if ts_str else ''
            msg = (ev.get('Message', '') or '').split('\n')[0][:120].strip()
            level = 'critical' if eid in {4648, 4703, 4704} else 'warn' if eid == 4625 else 'info'
            events.append({'id': eid, 'level': level, 'time': t, 'msg': msg})
        return events
    except Exception as e:
        log.warning(f'Event log fetch failed: {e}')
        return []


def collect():
    ip, mac = get_primary_ip_mac()
    user, session_start = get_logged_in_user()
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk_path = 'C:\\' if platform.system() == 'Windows' else '/'
    disk = psutil.disk_usage(disk_path)
    return {
        'hostname': socket.gethostname(),
        'ip': ip, 'mac': mac,
        'os': f"{platform.system()} {platform.release()} {platform.version()[:30]}",
        'domain': '', 'user': user, 'session_start': session_start,
        'cpu': int(cpu), 'ram': int(mem.percent), 'disk': int(disk.percent),
        'processes': get_processes(),
        'events': get_events_powershell(),
    }


def try_get_domain(payload):
    try:
        r = subprocess.run(['powershell', '-NonInteractive', '-NoProfile', '-Command', '(Get-WmiObject Win32_ComputerSystem).Domain'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            payload['domain'] = r.stdout.strip()
    except Exception:
        pass
    return payload


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    log.info(f'SecNet agent starting — {args.url} every {INTERVAL}s')
    while True:
        try:
            payload = collect()
            payload = try_get_domain(payload)
            resp = report(args.url, args.key, payload)
            log.info(f'Reported {payload["hostname"]} — status: {resp.get("status","?")}')
        except Exception as e:
            log.error(f'Report failed: {e}')
        if args.once:
            break
        time.sleep(INTERVAL)

if __name__ == '__main__':
    main()
