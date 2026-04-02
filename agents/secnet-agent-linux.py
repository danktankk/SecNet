#!/usr/bin/env python3
"""
SecNet Linux Agent
Collects system stats, processes, and auth log events,
then POSTs to the SecNet dashboard every 30 seconds.

Can run standalone (console) or as a systemd service.

Requirements: pip install psutil requests

Setup:
  1. sudo python3 secnet-agent-linux.py setup --url http://SECNET:8088 --key YOUR_KEY
  2. sudo python3 secnet-agent-linux.py install
  3. sudo systemctl start secnet-agent

Commands:
  setup   — create config file (/etc/secnet/agent.json)
  install — install systemd service unit + copy agent to /usr/local/bin
  run     — run in console (foreground, for testing)
  status  — show config and service status
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

# ── Config ────────────────────────────────────────────────

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


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, mode=0o755, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


# ── Collection ────────────────────────────────────────────

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
    return os.environ.get('USER', 'unknown'), int(time.time())


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


def get_events_journalctl():
    try:
        result = subprocess.run(
            ['journalctl', '-u', 'ssh', '-u', 'sshd', '--no-pager', '-n', str(MAX_EVENTS), '--output', 'json'],
            capture_output=True, text=True, timeout=10
        )
        events = []
        for line in result.stdout.strip().splitlines():
            try:
                entry = json.loads(line)
                msg = entry.get('MESSAGE', '')
                ts = int(entry.get('__REALTIME_TIMESTAMP', 0)) // 1000000
                t = time.strftime('%H:%M:%S', time.localtime(ts)) if ts else ''
                level = 'warn' if any(w in msg.lower() for w in ['failed', 'invalid', 'error']) else 'info'
                events.append({'id': 0, 'level': level, 'time': t, 'msg': msg[:120]})
            except Exception:
                continue
        return events
    except FileNotFoundError:
        return get_events_authlog()
    except Exception as e:
        log.warning(f'journalctl failed: {e}')
        return get_events_authlog()


def get_events_authlog():
    try:
        result = subprocess.run(['tail', '-n', '100', '/var/log/auth.log'],
                                capture_output=True, text=True, timeout=5)
        events = []
        for line in result.stdout.strip().splitlines()[-MAX_EVENTS:]:
            level = 'warn' if any(w in line.lower() for w in ['failed', 'invalid', 'error']) else 'info'
            parts = line.split()
            t = ' '.join(parts[0:3]) if len(parts) >= 3 else ''
            events.append({'id': 0, 'level': level, 'time': t, 'msg': line[:120]})
        return events
    except Exception:
        return []


def collect():
    ip, mac = get_primary_ip_mac()
    user, session_start = get_logged_in_user()
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    distro = ''
    try:
        distro = platform.freedesktop_os_release().get('PRETTY_NAME', '')
    except Exception:
        distro = platform.version()[:40]
    return {
        'hostname': socket.gethostname(),
        'ip': ip, 'mac': mac,
        'os': distro or f"Linux {platform.release()}",
        'domain': '',
        'user': user, 'session_start': session_start,
        'cpu': int(cpu), 'ram': int(mem.percent), 'disk': int(disk.percent),
        'processes': get_processes(),
        'events': get_events_journalctl(),
    }


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Agent loop ────────────────────────────────────────────

def agent_loop(url: str, key: str):
    global _running
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    log.info(f'SecNet agent starting — reporting to {url} every {INTERVAL}s')
    while _running:
        try:
            payload = collect()
            resp = report(url, key, payload)
            log.info(f'Reported {payload["hostname"]} — status: {resp.get("status","?")}')
        except Exception as e:
            log.error(f'Report failed: {e}')
        for _ in range(INTERVAL):
            if not _running:
                break
            time.sleep(1)
    log.info('SecNet agent stopped')


# ── CLI Commands ──────────────────────────────────────────

SYSTEMD_UNIT = f"""[Unit]
Description=SecNet Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={INSTALL_PATH} run
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""


def cmd_setup(args):
    cfg = load_config()
    if args.url:
        cfg['url'] = args.url.rstrip('/')
    if args.key:
        cfg['key'] = args.key
    if not cfg.get('url') or not cfg.get('key'):
        print('ERROR: --url and --key are required (or must already be in config)')
        sys.exit(1)
    save_config(cfg)
    print(f'Config saved to {CONFIG_FILE}')
    print(f'  URL: {cfg["url"]}')
    print(f'  Key: {cfg["key"][:8]}...')
    try:
        r = requests.get(f'{cfg["url"]}/api/health', timeout=5)
        print(f'  Connection test: {"OK" if r.status_code == 200 else f"HTTP {r.status_code}"}')
    except Exception as e:
        print(f'  Connection test: FAILED ({e})')


def cmd_install(args):
    if os.geteuid() != 0:
        print('ERROR: install requires root. Run with sudo.')
        sys.exit(1)
    cfg = load_config()
    if not cfg.get('url') or not cfg.get('key'):
        print('ERROR: Run setup first: sudo secnet-agent setup --url URL --key KEY')
        sys.exit(1)
    # Copy script to /usr/local/bin
    src = os.path.abspath(__file__)
    shutil.copy2(src, INSTALL_PATH)
    os.chmod(INSTALL_PATH, 0o755)
    print(f'Installed agent to {INSTALL_PATH}')
    # Write systemd unit
    with open(SERVICE_UNIT, 'w') as f:
        f.write(SYSTEMD_UNIT)
    print(f'Created service unit at {SERVICE_UNIT}')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'secnet-agent'], check=True)
    print('Service enabled. Start with: sudo systemctl start secnet-agent')


def cmd_status(args):
    cfg = load_config()
    if cfg:
        print(f'Config: {CONFIG_FILE}')
        print(f'  URL: {cfg.get("url", "(not set)")}')
        print(f'  Key: {cfg.get("key", "(not set)")[:8]}...' if cfg.get('key') else '  Key: (not set)')
    else:
        print(f'No config found at {CONFIG_FILE}')
    print()
    result = subprocess.run(['systemctl', 'is-active', 'secnet-agent'], capture_output=True, text=True)
    state = result.stdout.strip()
    print(f'Service: {state}')
    if state == 'active':
        result2 = subprocess.run(['systemctl', 'show', 'secnet-agent', '--property=ActiveEnterTimestamp'], capture_output=True, text=True)
        print(f'  {result2.stdout.strip()}')


def cmd_run(args):
    cfg = load_config()
    url = getattr(args, 'url', '') or cfg.get('url', '')
    key = getattr(args, 'key', '') or cfg.get('key', '')
    if not url or not key:
        print('ERROR: No config. Run setup first, or pass --url and --key')
        sys.exit(1)
    agent_loop(url, key)


def main():
    parser = argparse.ArgumentParser(
        description='SecNet Linux Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick start:
  sudo python3 secnet-agent-linux.py setup --url http://192.168.160.161:8088 --key YOUR_KEY
  sudo python3 secnet-agent-linux.py install
  sudo systemctl start secnet-agent
  sudo systemctl status secnet-agent
        """
    )
    sub = parser.add_subparsers(dest='command')

    p_setup = sub.add_parser('setup', help='Create/update config file')
    p_setup.add_argument('--url', help='SecNet dashboard URL')
    p_setup.add_argument('--key', help='Agent API key')

    sub.add_parser('status', help='Show config and service status')

    p_run = sub.add_parser('run', help='Run in console (foreground)')
    p_run.add_argument('--url', default='')
    p_run.add_argument('--key', default='')

    sub.add_parser('install', help='Install systemd service (requires root)')

    # Legacy compat
    parser.add_argument('--url', default='', help=argparse.SUPPRESS)
    parser.add_argument('--key', default='', help=argparse.SUPPRESS)
    parser.add_argument('--once', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()

    if not args.command and (args.url and args.key):
        if args.once:
            payload = collect()
            resp = report(args.url, args.key, payload)
            print(json.dumps(resp))
        else:
            agent_loop(args.url, args.key)
        return

    commands = {'setup': cmd_setup, 'status': cmd_status, 'run': cmd_run, 'install': cmd_install}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
