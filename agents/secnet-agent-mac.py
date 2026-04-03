#!/usr/bin/env python3
"""
SecNet macOS Agent
Collects system stats, top processes, and security log events,
then POSTs to the SecNet dashboard every 30 seconds.

Runs as a launchd service. Use the install script for setup:

  sudo bash install-mac.sh --url http://SECNET:8088 --key YOUR_KEY

That script handles everything: deps, config, launchd plist, load.

Or manually:
  pip3 install psutil requests
  sudo python3 secnet-agent-mac.py setup --url http://SECNET:8088 --key YOUR_KEY
  sudo python3 secnet-agent-mac.py install
  sudo launchctl load /Library/LaunchDaemons/com.secnet.agent.plist

Config:  /etc/secnet/agent.json
Logs:    /Library/Logs/secnet-agent.log
"""
import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import threading
import logging
import signal

import psutil
import requests

CONFIG_DIR = '/etc/secnet'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'agent.json')
INSTALL_PATH = '/usr/local/bin/secnet-agent'
PLIST_PATH = '/Library/LaunchDaemons/com.secnet.agent.plist'
LOG_FILE = '/Library/Logs/secnet-agent.log'

AGENT_VERSION = "0.11.1"
INTERVAL = 30
MAX_PROCS = 40
MAX_EVENTS = 30

# Logical CPU count for normalizing per-process cpu_percent
_cpu_count = psutil.cpu_count(logical=True) or 1

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('secnet-agent')
_stop = threading.Event()


def _handle_signal(signum, frame):
    _stop.set()


def load_config():
    if not os.path.exists(CONFIG_FILE): return {}
    with open(CONFIG_FILE) as f: return json.load(f)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, mode=0o755, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f: json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def get_primary_ip_mac():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]; s.close()
    except: ip = '127.0.0.1'
    mac = ''
    for _, addrs in psutil.net_if_addrs().items():
        for addr in addrs:
            if addr.address == ip:
                for a2 in addrs:
                    if a2.family == psutil.AF_LINK: mac = a2.address
                break
    return ip, mac


def get_processes():
    procs = []
    for p in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_info']):
        try:
            i = p.info
            procs.append({'name': i['name'] or '', 'pid': i['pid'],
                          'cpu': round((i['cpu_percent'] or 0) / _cpu_count, 1),
                          'ram': int((i['memory_info'].rss if i['memory_info'] else 0) / 1048576)})
        except: continue
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:MAX_PROCS]


def get_events():
    try:
        result = subprocess.run([
            'log', 'show',
            '--predicate', 'subsystem == "com.apple.securityd" OR subsystem == "com.openssh.sshd" OR category == "authentication"',
            '--last', '1h', '--style', 'ndjson', '--info'
        ], capture_output=True, text=True, timeout=15)
        events = []
        for line in result.stdout.strip().splitlines()[-MAX_EVENTS:]:
            try:
                entry = json.loads(line)
                msg = entry.get('eventMessage', '')[:300]
                ts = entry.get('timestamp', '')
                t = ts[11:19] if len(ts) >= 19 else ''
                level = 'warn' if any(w in msg.lower() for w in ['fail', 'deny', 'error', 'invalid']) else 'info'
                events.append({'id': 0, 'level': level, 'time': t, 'msg': msg})
            except: continue
        return events
    except Exception as e:
        log.warning(f'macOS log failed: {e}')
        return []


def collect():
    ip, mac_addr = get_primary_ip_mac()
    try:
        users = psutil.users()
        user, ss = (users[0].name, int(users[0].started)) if users else (os.environ.get('USER', '?'), int(time.time()))
    except: user, ss = os.environ.get('USER', '?'), int(time.time())
    mac_ver = platform.mac_ver()[0]
    return {
        'hostname': socket.gethostname(), 'ip': ip, 'mac': mac_addr,
        'os': f"macOS {mac_ver}" if mac_ver else f"macOS {platform.release()}",
        'domain': '', 'user': user, 'session_start': ss,
        'cpu': int(psutil.cpu_percent(interval=None)),
        'ram': int(psutil.virtual_memory().percent),
        'disk': int(psutil.disk_usage('/').percent),
        'processes': get_processes(), 'events': get_events(),
    }


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status(); return r.json()


def agent_loop(url, key):
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info(f'Reporting to {url} every {INTERVAL}s')
    # Prime CPU measurement counters — first non-blocking call always returns 0.0
    psutil.cpu_percent(interval=None)
    for p in psutil.process_iter():
        try: p.cpu_percent(interval=None)
        except: pass
    # First wait establishes the measurement window for cpu_percent(interval=None)
    _stop.wait(INTERVAL)
    while not _stop.is_set():
        try:
            resp = report(url, key, collect())
            log.info(f'Reported {socket.gethostname()} — {resp.get("status","?")}')
        except Exception as e: log.error(f'Report failed: {e}')
        _stop.wait(INTERVAL)


LAUNCHD_PLIST_CONTENT = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.secnet.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/secnet-venv/bin/python</string>
        <string>/usr/local/bin/secnet-agent</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/Library/Logs/secnet-agent.log</string>
    <key>StandardErrorPath</key><string>/Library/Logs/secnet-agent.log</string>
    <key>ThrottleInterval</key><integer>10</integer>
</dict>
</plist>
"""


def main():
    parser = argparse.ArgumentParser(prog='secnet-agent', description='SecNet macOS Agent')
    sub = parser.add_subparsers(dest='command')

    p_setup = sub.add_parser('setup', help='Save URL and key to /etc/secnet/agent.json')
    p_setup.add_argument('--url', required=True, help='SecNet dashboard URL (e.g. http://192.168.160.161:8088)')
    p_setup.add_argument('--key', required=True, help='Agent key (must match WORKSTATION_AGENT_KEY in server .env)')

    sub.add_parser('install', help='Copy agent to /usr/local/bin, create launchd plist')
    sub.add_parser('run', help='Run agent in foreground (used by launchd, or for testing)')
    sub.add_parser('status', help='Show config and service status')

    args = parser.parse_args()

    if args.command == 'setup':
        save_config({'url': args.url.rstrip('/'), 'key': args.key})
        print(f'Config saved to {CONFIG_FILE}')
        try:
            r = requests.get(f'{args.url.rstrip("/")}/api/health', timeout=5)
            print(f'  Connection: {"OK" if r.status_code == 200 else f"HTTP {r.status_code}"}')
        except Exception as e:
            print(f'  Connection: FAILED ({e})')

    elif args.command == 'install':
        if os.geteuid() != 0: print('ERROR: requires root. Run with sudo.'); sys.exit(1)
        cfg = load_config()
        if not cfg.get('url') or not cfg.get('key'):
            print('ERROR: Run setup first.'); sys.exit(1)
        shutil.copy2(os.path.abspath(__file__), INSTALL_PATH)
        os.chmod(INSTALL_PATH, 0o755)
        with open(PLIST_PATH, 'w') as f: f.write(LAUNCHD_PLIST_CONTENT)
        print(f'Installed to {INSTALL_PATH}')
        print(f'Load with: sudo launchctl load {PLIST_PATH}')

    elif args.command == 'run':
        cfg = load_config()
        if not cfg.get('url') or not cfg.get('key'):
            print(f'ERROR: No config at {CONFIG_FILE}. Run setup first.'); sys.exit(1)
        agent_loop(cfg['url'], cfg['key'])

    elif args.command == 'status':
        cfg = load_config()
        if cfg:
            print(f'Config: {CONFIG_FILE}')
            print(f'  URL: {cfg.get("url", "(not set)")}')
            print(f'  Key: {cfg.get("key", "")[:8]}...' if cfg.get('key') else '  Key: (not set)')
        else:
            print(f'No config at {CONFIG_FILE}')
        r = subprocess.run(['launchctl', 'list', 'com.secnet.agent'], capture_output=True, text=True)
        if r.returncode == 0:
            print(f'Service: LOADED')
        else:
            print(f'Service: NOT LOADED')
        if os.path.exists(LOG_FILE):
            print(f'Log: {LOG_FILE}')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
