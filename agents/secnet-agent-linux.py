#!/usr/bin/env python3
"""
SecNet Linux Agent
Collects system stats, top processes, and SSH auth events,
then POSTs to the SecNet dashboard every 30 seconds.

Runs as a systemd service. Use the install script for setup:

  sudo bash install-linux.sh --url http://SECNET:8088 --key YOUR_KEY

That script handles everything: deps, config, systemd unit, start.

Or manually:
  pip3 install psutil requests
  sudo python3 secnet-agent-linux.py setup --url http://SECNET:8088 --key YOUR_KEY
  sudo python3 secnet-agent-linux.py install
  sudo systemctl start secnet-agent

Config:  /etc/secnet/agent.json
Logs:    journalctl -u secnet-agent -f
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
import logging
import signal

import psutil
import requests

CONFIG_DIR = '/etc/secnet'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'agent.json')
INSTALL_PATH = '/usr/local/bin/secnet-agent'
SERVICE_UNIT = '/etc/systemd/system/secnet-agent.service'

INTERVAL = 30
MAX_PROCS = 40
MAX_EVENTS = 30

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('secnet-agent')
_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


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
                          'cpu': round(i['cpu_percent'] or 0, 1),
                          'ram': int((i['memory_info'].rss if i['memory_info'] else 0) / 1048576)})
        except: continue
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:MAX_PROCS]


def get_events():
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'ssh', '-u', 'sshd', '--no-pager', '-n', str(MAX_EVENTS), '--output', 'json'],
            capture_output=True, text=True, timeout=10)
        events = []
        for line in result.stdout.strip().splitlines():
            try:
                entry = json.loads(line)
                msg = entry.get('MESSAGE', '')
                ts = int(entry.get('__REALTIME_TIMESTAMP', 0)) // 1000000
                t = time.strftime('%H:%M:%S', time.localtime(ts)) if ts else ''
                level = 'warn' if any(w in msg.lower() for w in ['failed', 'invalid', 'error']) else 'info'
                events.append({'id': 0, 'level': level, 'time': t, 'msg': msg[:300]})
            except: continue
        return events
    except FileNotFoundError:
        pass
    except: pass
    # Fallback: /var/log/auth.log
    try:
        result = subprocess.run(['tail', '-n', '100', '/var/log/auth.log'], capture_output=True, text=True, timeout=5)
        events = []
        for line in result.stdout.strip().splitlines()[-MAX_EVENTS:]:
            level = 'warn' if any(w in line.lower() for w in ['failed', 'invalid', 'error']) else 'info'
            events.append({'id': 0, 'level': level, 'time': '', 'msg': line[:300]})
        return events
    except: return []


def collect():
    ip, mac = get_primary_ip_mac()
    try:
        users = psutil.users()
        user, ss = (users[0].name, int(users[0].started)) if users else (os.environ.get('USER', '?'), int(time.time()))
    except: user, ss = os.environ.get('USER', '?'), int(time.time())
    distro = ''
    try: distro = platform.freedesktop_os_release().get('PRETTY_NAME', '')
    except: distro = platform.version()[:40]
    return {
        'hostname': socket.gethostname(), 'ip': ip, 'mac': mac,
        'os': distro or f"Linux {platform.release()}", 'domain': '',
        'user': user, 'session_start': ss,
        'cpu': int(psutil.cpu_percent(interval=1)),
        'ram': int(psutil.virtual_memory().percent),
        'disk': int(psutil.disk_usage('/').percent),
        'processes': get_processes(), 'events': get_events(),
    }


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status(); return r.json()


def agent_loop(url, key):
    global _running
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info(f'Reporting to {url} every {INTERVAL}s')
    while _running:
        try:
            resp = report(url, key, collect())
            log.info(f'Reported {socket.gethostname()} — {resp.get("status","?")}')
        except Exception as e: log.error(f'Report failed: {e}')
        for _ in range(INTERVAL):
            if not _running: break
            time.sleep(1)


SYSTEMD_UNIT_CONTENT = """[Unit]
Description=SecNet Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/secnet-agent run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


def main():
    parser = argparse.ArgumentParser(prog='secnet-agent', description='SecNet Linux Agent')
    sub = parser.add_subparsers(dest='command')

    p_setup = sub.add_parser('setup', help='Save URL and key to /etc/secnet/agent.json')
    p_setup.add_argument('--url', required=True, help='SecNet dashboard URL (e.g. http://192.168.160.161:8088)')
    p_setup.add_argument('--key', required=True, help='Agent key (must match WORKSTATION_AGENT_KEY in server .env)')

    sub.add_parser('install', help='Copy agent to /usr/local/bin, create systemd service, enable it')
    sub.add_parser('run', help='Run agent in foreground (used by systemd, or for testing)')
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
        with open(SERVICE_UNIT, 'w') as f: f.write(SYSTEMD_UNIT_CONTENT)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', 'enable', 'secnet-agent'], check=True)
        print(f'Installed to {INSTALL_PATH}')
        print(f'Service enabled. Start: sudo systemctl start secnet-agent')

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
        r = subprocess.run(['systemctl', 'is-active', 'secnet-agent'], capture_output=True, text=True)
        print(f'Service: {r.stdout.strip()}')

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
