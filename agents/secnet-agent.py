#!/usr/bin/env python3
"""
SecNet Windows Agent — standalone EXE that installs as a Windows Service.
Compatible with Windows 10 and Windows 11.

Build:  pip install pyinstaller psutil requests pywin32
        pyinstaller --onefile --name secnet-agent --hidden-import=win32timezone secnet-agent.py

Usage (run as Administrator):
  secnet-agent.exe setup  --url http://SECNET:8088 --key YOUR_KEY
  secnet-agent.exe install
  secnet-agent.exe start
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

import psutil
import requests

# ── Paths ─────────────────────────────────────────────────

PROGRAM_DIR = os.path.join(os.environ.get('PROGRAMFILES', 'C:\\Program Files'), 'SecNet')
CONFIG_DIR = os.path.join(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'), 'SecNet')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'agent.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'agent.log')
INSTALL_EXE = os.path.join(PROGRAM_DIR, 'secnet-agent.exe')
SERVICE_NAME = 'SecNetAgent'
SERVICE_DISPLAY = 'SecNet Monitoring Agent'
SERVICE_DESC = 'Reports workstation health and security events to SecNet dashboard'

INTERVAL = 30
MAX_PROCS = 40
MAX_EVENTS = 30
SECURITY_EVENT_IDS = {4624, 4625, 4648, 4688, 4703, 4704, 4776, 4800, 4801, 5156, 7045}


def _setup_logging(to_file=False):
    handlers = [logging.StreamHandler()]
    if to_file:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        handlers.append(logging.FileHandler(LOG_FILE))
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=handlers, force=True)
    return logging.getLogger('secnet-agent')


log = _setup_logging()


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)


# ── Cached values (computed once, not every cycle) ────────

_cached_domain: str | None = None
_cached_os_version: str | None = None


def get_os_version():
    global _cached_os_version
    if _cached_os_version:
        return _cached_os_version
    release = platform.release()
    version = platform.version()
    build = 0
    try:
        build = int(version.split('.')[-1]) if version else 0
    except ValueError:
        pass
    name = 'Windows 11' if release == '10' and build >= 22000 else f'Windows {release}'
    _cached_os_version = f"{name} ({version[:20]})"
    return _cached_os_version


def get_domain():
    """Get AD domain. Cached — domain doesn't change at runtime."""
    global _cached_domain
    if _cached_domain is not None:
        return _cached_domain
    # Try native Python first (no subprocess)
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(256)
        size = ctypes.c_ulong(256)
        ctypes.windll.kernel32.GetComputerNameExW(2, buf, ctypes.byref(size))  # 2 = ComputerNameDnsDomain
        if buf.value:
            _cached_domain = buf.value
            return _cached_domain
    except Exception:
        pass
    # Fallback: WMI via PowerShell (one-time only)
    for cmd in ('(Get-CimInstance Win32_ComputerSystem).Domain', '(Get-WmiObject Win32_ComputerSystem).Domain'):
        try:
            r = subprocess.run(['powershell', '-NonInteractive', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', cmd],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                _cached_domain = r.stdout.strip()
                return _cached_domain
        except Exception:
            continue
    _cached_domain = ''
    return _cached_domain


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


def get_events_native():
    """Read Windows Security Event Log using win32evtlog (no PowerShell subprocess)."""
    try:
        import win32evtlog
        import win32evtlogutil
    except ImportError:
        return _get_events_powershell_fallback()

    try:
        hand = win32evtlog.OpenEventLog(None, 'Security')
    except Exception:
        return _get_events_powershell_fallback()

    events = []
    flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    seen = 0
    max_scan = 200  # scan at most 200 events looking for our IDs

    try:
        while seen < max_scan and len(events) < MAX_EVENTS:
            records = win32evtlog.ReadEventLog(hand, flags, 0)
            if not records:
                break
            for ev in records:
                seen += 1
                if seen > max_scan:
                    break
                eid = ev.EventID & 0xFFFF  # mask to 16-bit
                if eid not in SECURITY_EVENT_IDS:
                    continue
                t = ev.TimeGenerated.strftime('%H:%M:%S') if ev.TimeGenerated else ''
                # Build message from string inserts
                msg = ''
                try:
                    msg = win32evtlogutil.SafeFormatMessage(ev, 'Security')
                    msg = msg.split('\n')[0][:120].strip()
                except Exception:
                    msg = f'Event {eid}'
                level = 'critical' if eid in {4648, 4703, 4704} else 'warn' if eid == 4625 else 'info'
                events.append({'id': eid, 'level': level, 'time': t, 'msg': msg})
                if len(events) >= MAX_EVENTS:
                    break
    except Exception as e:
        log.warning(f'Native event log read failed: {e}')
    finally:
        try:
            win32evtlog.CloseEventLog(hand)
        except Exception:
            pass

    return events


def _get_events_powershell_fallback():
    """Fallback if win32evtlog isn't available."""
    ids = ','.join(str(i) for i in SECURITY_EVENT_IDS)
    ps = (
        f"Get-WinEvent -LogName Security -MaxEvents 100 -ErrorAction SilentlyContinue | "
        f"Where-Object {{$_.Id -in @({ids})}} | "
        f"Select-Object -First {MAX_EVENTS} Id,TimeCreated,Message | "
        f"ConvertTo-Json -Compress"
    )
    try:
        r = subprocess.run(
            ['powershell', '-NonInteractive', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        raw = json.loads(r.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        events = []
        for ev in raw:
            eid = ev.get('Id', 0)
            ts = ev.get('TimeCreated', {})
            ts_str = ''
            if isinstance(ts, dict):
                ts_str = ts.get('value', ts.get('Value', ts.get('DateTime', '')))
            elif isinstance(ts, str):
                ts_str = ts
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
        log.warning(f'PowerShell event log fallback failed: {e}')
        return []


def collect():
    ip, mac = get_primary_ip_mac()
    user, session_start = get_logged_in_user()
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('C:\\')
    return {
        'hostname': socket.gethostname(),
        'ip': ip, 'mac': mac,
        'os': get_os_version(),
        'domain': get_domain(),
        'user': user, 'session_start': session_start,
        'cpu': int(cpu), 'ram': int(mem.percent), 'disk': int(disk.percent),
        'processes': get_processes(),
        'events': get_events_native(),
    }


def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status()
    return r.json()


# ── Agent loop ────────────────────────────────────────────

def agent_loop(url: str, key: str, stop_event=None):
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
        for _ in range(INTERVAL):
            if stop_event and stop_event.is_set():
                break
            time.sleep(1)
    log.info('SecNet agent stopped')


# ── Windows Service ───────────────────────────────────────

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

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)

        def SvcDoRun(self):
            import threading
            global log
            log = _setup_logging(to_file=True)

            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (self._svc_name_, ''))

            cfg = load_config()
            url = cfg.get('url', '')
            key = cfg.get('key', '')
            if not url or not key:
                log.error(f'No config at {CONFIG_FILE}. Run: secnet-agent setup --url URL --key KEY')
                return

            stop_evt = threading.Event()

            def _watch():
                win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE)
                stop_evt.set()

            threading.Thread(target=_watch, daemon=True).start()
            agent_loop(url, key, stop_event=stop_evt)

    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


# ── CLI Commands ──────────────────────────────────────────

def _exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)


def cmd_setup(args):
    cfg = load_config()
    if args.url:
        cfg['url'] = args.url.rstrip('/')
    if args.key:
        cfg['key'] = args.key
    if not cfg.get('url') or not cfg.get('key'):
        print('ERROR: --url and --key are required')
        sys.exit(1)
    save_config(cfg)
    print(f'Config saved to {CONFIG_FILE}')
    print(f'  URL: {cfg["url"]}')
    print(f'  Key: {cfg["key"][:8]}...')
    try:
        r = requests.get(f'{cfg["url"]}/api/health', timeout=5)
        print(f'  Connection: {"OK" if r.status_code == 200 else f"HTTP {r.status_code}"}')
    except Exception as e:
        print(f'  Connection: FAILED ({e})')
    print(f'  OS: {get_os_version()}')


def cmd_install(args):
    if not HAS_WIN32:
        print('ERROR: pywin32 required (should be bundled in the exe)')
        sys.exit(1)
    cfg = load_config()
    if not cfg.get('url') or not cfg.get('key'):
        print('ERROR: Run setup first: secnet-agent setup --url URL --key KEY')
        sys.exit(1)

    src = _exe_path()
    os.makedirs(PROGRAM_DIR, exist_ok=True)
    if os.path.normpath(src) != os.path.normpath(INSTALL_EXE):
        shutil.copy2(src, INSTALL_EXE)
        print(f'Copied to {INSTALL_EXE}')

    subprocess.run([
        'sc', 'create', SERVICE_NAME,
        f'binPath={INSTALL_EXE} --run-service',
        f'DisplayName={SERVICE_DISPLAY}',
        'start=auto',
    ], check=True)
    subprocess.run(['sc', 'description', SERVICE_NAME, SERVICE_DESC], check=True)
    subprocess.run(['sc', 'failure', SERVICE_NAME, 'reset=86400',
                     'actions=restart/10000/restart/30000/restart/60000'], check=True)
    print(f'Service "{SERVICE_NAME}" installed (auto-start on boot)')
    print(f'Start now: secnet-agent start')


def cmd_remove(args):
    subprocess.run(['sc', 'stop', SERVICE_NAME], capture_output=True)
    time.sleep(2)
    subprocess.run(['sc', 'delete', SERVICE_NAME], check=True)
    print(f'Service "{SERVICE_NAME}" removed')
    if os.path.exists(INSTALL_EXE):
        try:
            os.remove(INSTALL_EXE)
            print(f'Removed {INSTALL_EXE}')
        except Exception:
            print(f'Note: could not remove {INSTALL_EXE} (may be in use)')


def cmd_start(args):
    subprocess.run(['sc', 'start', SERVICE_NAME], check=True)
    print(f'Service starting...')
    time.sleep(2)
    result = subprocess.run(['sc', 'query', SERVICE_NAME], capture_output=True, text=True)
    if 'RUNNING' in result.stdout:
        print('Service is RUNNING')
    else:
        print('Service may still be starting — check: secnet-agent status')


def cmd_stop(args):
    subprocess.run(['sc', 'stop', SERVICE_NAME], check=True)
    print('Service stopped')


def cmd_status(args):
    cfg = load_config()
    if cfg:
        print(f'Config:  {CONFIG_FILE}')
        print(f'  URL:   {cfg.get("url", "(not set)")}')
        print(f'  Key:   {cfg.get("key", "")[:8]}...' if cfg.get('key') else '  Key:   (not set)')
    else:
        print(f'Config:  NOT FOUND at {CONFIG_FILE}')
    print()
    result = subprocess.run(['sc', 'query', SERVICE_NAME], capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if 'STATE' in line or 'SERVICE_NAME' in line:
                print(f'  {line}')
    else:
        print('Service: NOT INSTALLED')
    print()
    print(f'Exe:     {INSTALL_EXE}  {"(exists)" if os.path.exists(INSTALL_EXE) else "(not found)"}')
    print(f'Log:     {LOG_FILE}  {"(exists)" if os.path.exists(LOG_FILE) else "(not found)"}')
    print(f'OS:      {get_os_version()}')


def cmd_run(args):
    global log
    log = _setup_logging(to_file=False)
    cfg = load_config()
    url = args.url or cfg.get('url', '')
    key = args.key or cfg.get('key', '')
    if not url or not key:
        print('ERROR: No config. Run setup first, or pass --url and --key')
        sys.exit(1)
    agent_loop(url, key)


def _run_as_service():
    if not HAS_WIN32:
        sys.exit(1)
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(SecNetService)
    servicemanager.StartServiceCtrlDispatcher()


def main():
    if '--run-service' in sys.argv:
        _run_as_service()
        return

    parser = argparse.ArgumentParser(
        prog='secnet-agent',
        description='SecNet Workstation Agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Quick start (run as Administrator):
  secnet-agent setup --url http://192.168.160.161:8088 --key YOUR_KEY
  secnet-agent install
  secnet-agent start
  secnet-agent status
        """
    )
    sub = parser.add_subparsers(dest='command')

    p_setup = sub.add_parser('setup', help='Save config (URL + key)')
    p_setup.add_argument('--url', help='SecNet dashboard URL')
    p_setup.add_argument('--key', help='Agent API key')

    sub.add_parser('install', help='Install Windows service (admin)')
    sub.add_parser('remove', help='Remove Windows service (admin)')
    sub.add_parser('start', help='Start the service (admin)')
    sub.add_parser('stop', help='Stop the service (admin)')
    sub.add_parser('status', help='Show config + service status')

    p_run = sub.add_parser('run', help='Run in console (foreground)')
    p_run.add_argument('--url', default='')
    p_run.add_argument('--key', default='')

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

    commands = {
        'setup': cmd_setup, 'install': cmd_install, 'remove': cmd_remove,
        'start': cmd_start, 'stop': cmd_stop, 'status': cmd_status, 'run': cmd_run,
    }
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
