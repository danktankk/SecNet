#!/usr/bin/env python3
"""
SecNet Windows Agent
Collects system stats, processes, and event log entries,
then POSTs to the SecNet dashboard every 30 seconds.

Can run standalone (console) or as a Windows Service.

Requirements: pip install psutil requests pywin32

Setup:
  1. python secnet-agent.py setup --url http://SECNET:8088 --key YOUR_KEY
  2. python secnet-agent.py install
  3. python secnet-agent.py start

Commands:
  setup   — create config file (C:\\ProgramData\\SecNet\\agent.json)
  install — install as Windows service (requires admin)
  start   — start the service
  stop    — stop the service
  remove  — uninstall the service
  run     — run in console (foreground, for testing)
  status  — show config and service status
"""
import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import time
import logging

import psutil
import requests

# ── Config ────────────────────────────────────────────────

CONFIG_DIR = os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'SecNet')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'agent.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'agent.log')
SERVICE_NAME = 'SecNetAgent'
SERVICE_DISPLAY = 'SecNet Monitoring Agent'
SERVICE_DESC = 'Reports workstation health and security events to SecNet dashboard'

INTERVAL = 30
MAX_PROCS = 40
MAX_EVENTS = 30
SECURITY_EVENT_IDS = {4624, 4625, 4648, 4688, 4703, 4704, 4776, 4800, 4801, 5156, 7045}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('secnet-agent')


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


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


def try_get_domain():
    try:
        r = subprocess.run(['powershell', '-NonInteractive', '-NoProfile', '-Command', '(Get-WmiObject Win32_ComputerSystem).Domain'], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return ''


def collect():
    ip, mac = get_primary_ip_mac()
    user, session_start = get_logged_in_user()
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('C:\\')
    return {
        'hostname': socket.gethostname(),
        'ip': ip, 'mac': mac,
        'os': f"{platform.system()} {platform.release()} {platform.version()[:30]}",
        'domain': try_get_domain(),
        'user': user, 'session_start': session_start,
        'cpu': int(cpu), 'ram': int(mem.percent), 'disk': int(disk.percent),
        'processes': get_processes(),
        'events': get_events_powershell(),
    }


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Agent loop ────────────────────────────────────────────

def agent_loop(url: str, key: str, stop_event=None):
    """Main collection loop. Runs until stop_event is set (service) or forever (console)."""
    log.info(f'SecNet agent starting — reporting to {url} every {INTERVAL}s')
    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            payload = collect()
            resp = report(url, key, payload)
            log.info(f'Reported {payload["hostname"]} — status: {resp.get("status","?")}')
        except Exception as e:
            log.error(f'Report failed: {e}')
        # Sleep in small increments so we can respond to stop quickly
        for _ in range(INTERVAL):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)


# ── Windows Service ───────────────────────────────────────

def _import_win32():
    """Import win32 modules — only needed for service operations."""
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    return win32serviceutil, win32service, win32event, servicemanager


try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager

    class SecNetService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY
        _svc_description_ = SERVICE_DESC

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._stop = False

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            self._stop = True
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            import threading
            # Set up file logging for service mode
            fh = logging.FileHandler(LOG_FILE)
            fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logging.getLogger().addHandler(fh)

            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (self._svc_name_, ''))

            cfg = load_config()
            url = cfg.get('url', '')
            key = cfg.get('key', '')
            if not url or not key:
                log.error(f'No config found at {CONFIG_FILE}. Run: secnet-agent setup --url URL --key KEY')
                servicemanager.LogErrorMsg(f'SecNet agent missing config at {CONFIG_FILE}')
                return

            stop_evt = threading.Event()

            def _watch_stop():
                win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
                stop_evt.set()

            t = threading.Thread(target=_watch_stop, daemon=True)
            t.start()
            agent_loop(url, key, stop_event=stop_evt)
            log.info('SecNet agent stopped')

    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


# ── CLI Commands ──────────────────────────────────────────

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
    # Quick connectivity test
    try:
        r = requests.get(f'{cfg["url"]}/api/health', timeout=5)
        if r.status_code == 200:
            print(f'  Connection test: OK')
        else:
            print(f'  Connection test: HTTP {r.status_code}')
    except Exception as e:
        print(f'  Connection test: FAILED ({e})')


def cmd_status(args):
    cfg = load_config()
    if cfg:
        print(f'Config: {CONFIG_FILE}')
        print(f'  URL: {cfg.get("url", "(not set)")}')
        print(f'  Key: {cfg.get("key", "(not set)")[:8]}...' if cfg.get('key') else '  Key: (not set)')
    else:
        print(f'No config found at {CONFIG_FILE}')
        print(f'Run: secnet-agent setup --url http://SECNET:8088 --key YOUR_KEY')
    print()
    if HAS_WIN32:
        try:
            status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
            state_map = {1: 'STOPPED', 2: 'START_PENDING', 3: 'STOP_PENDING', 4: 'RUNNING'}
            print(f'Service: {state_map.get(status[1], f"UNKNOWN ({status[1]})")}')
        except Exception:
            print('Service: NOT INSTALLED')
    else:
        print('Service: pywin32 not installed (pip install pywin32)')
    if os.path.exists(LOG_FILE):
        print(f'Log: {LOG_FILE}')


def cmd_run(args):
    """Run in console (foreground) for testing."""
    cfg = load_config()
    url = args.url or cfg.get('url', '')
    key = args.key or cfg.get('key', '')
    if not url or not key:
        print('ERROR: No config. Run setup first, or pass --url and --key')
        sys.exit(1)
    agent_loop(url, key)


def cmd_install(args):
    if not HAS_WIN32:
        print('ERROR: pywin32 required. Run: pip install pywin32')
        sys.exit(1)
    cfg = load_config()
    if not cfg.get('url') or not cfg.get('key'):
        print('ERROR: Run setup first: secnet-agent setup --url URL --key KEY')
        sys.exit(1)
    # Install the service pointing to this script
    sys.argv = ['secnet-agent', 'install']
    win32serviceutil.HandleCommandLine(SecNetService)


def cmd_remove(args):
    if not HAS_WIN32:
        print('ERROR: pywin32 required.')
        sys.exit(1)
    sys.argv = ['secnet-agent', 'remove']
    win32serviceutil.HandleCommandLine(SecNetService)


def cmd_start(args):
    if not HAS_WIN32:
        print('ERROR: pywin32 required.')
        sys.exit(1)
    sys.argv = ['secnet-agent', 'start']
    win32serviceutil.HandleCommandLine(SecNetService)


def cmd_stop(args):
    if not HAS_WIN32:
        print('ERROR: pywin32 required.')
        sys.exit(1)
    sys.argv = ['secnet-agent', 'stop']
    win32serviceutil.HandleCommandLine(SecNetService)


def main():
    parser = argparse.ArgumentParser(
        description='SecNet Workstation Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick start:
  secnet-agent setup --url http://192.168.160.161:8088 --key YOUR_KEY
  secnet-agent install     (run as admin)
  secnet-agent start       (run as admin)
  secnet-agent status      (check everything)
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

    sub.add_parser('install', help='Install as Windows service (admin)')
    sub.add_parser('remove', help='Remove Windows service (admin)')
    sub.add_parser('start', help='Start the service (admin)')
    sub.add_parser('stop', help='Stop the service (admin)')

    # Legacy: support --url/--key without subcommand for backwards compat
    parser.add_argument('--url', default='', help=argparse.SUPPRESS)
    parser.add_argument('--key', default='', help=argparse.SUPPRESS)
    parser.add_argument('--once', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Legacy mode: if --url and --key passed without subcommand
    if not args.command and (args.url and args.key):
        log.info('Running in legacy mode (use "run" subcommand instead)')
        if args.once:
            try:
                payload = collect()
                resp = report(args.url, args.key, payload)
                print(json.dumps(resp))
            except Exception as e:
                print(f'ERROR: {e}', file=sys.stderr)
                sys.exit(1)
        else:
            agent_loop(args.url, args.key)
        return

    commands = {
        'setup': cmd_setup,
        'status': cmd_status,
        'run': cmd_run,
        'install': cmd_install,
        'remove': cmd_remove,
        'start': cmd_start,
        'stop': cmd_stop,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
