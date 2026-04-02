#!/usr/bin/env python3
"""SecNet Windows Agent"""
import json, os, platform, shutil, socket, subprocess, sys, time, logging, ctypes
import psutil, requests

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

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('secnet-agent')

def load_config():
    if not os.path.exists(CONFIG_FILE): return {}
    with open(CONFIG_FILE) as f: return json.load(f)

def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f: json.dump(cfg, f, indent=2)

# ── Cached values ─────────────────────────────────────────
_cached_domain = None
_cached_os = None

def get_os_version():
    global _cached_os
    if _cached_os: return _cached_os
    r, v = platform.release(), platform.version()
    try: b = int(v.split('.')[-1])
    except: b = 0
    name = 'Windows 11' if r == '10' and b >= 22000 else f'Windows {r}'
    _cached_os = f"{name} ({v[:20]})"
    return _cached_os

def get_domain():
    global _cached_domain
    if _cached_domain is not None: return _cached_domain
    try:
        buf = ctypes.create_unicode_buffer(256)
        sz = ctypes.c_ulong(256)
        ctypes.windll.kernel32.GetComputerNameExW(2, buf, ctypes.byref(sz))
        if buf.value: _cached_domain = buf.value; return _cached_domain
    except: pass
    _cached_domain = ''
    return _cached_domain

# ── Collection ────────────────────────────────────────────
def get_primary_ip_mac():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]; s.close()
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
            procs.append({'name': i['name'] or '', 'pid': i['pid'], 'cpu': round(i['cpu_percent'] or 0, 1),
                          'ram': int((i['memory_info'].rss if i['memory_info'] else 0) / 1048576)})
        except: continue
    procs.sort(key=lambda x: x['cpu'], reverse=True)
    return procs[:MAX_PROCS]

def get_events():
    try:
        import win32evtlog, win32evtlogutil
        hand = win32evtlog.OpenEventLog(None, 'Security')
        events, seen = [], 0
        flags = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
        while seen < 200 and len(events) < MAX_EVENTS:
            recs = win32evtlog.ReadEventLog(hand, flags, 0)
            if not recs: break
            for ev in recs:
                seen += 1
                if seen > 200: break
                eid = ev.EventID & 0xFFFF
                if eid not in SECURITY_EVENT_IDS: continue
                t = ev.TimeGenerated.strftime('%H:%M:%S') if ev.TimeGenerated else ''
                try: msg = ' '.join(line.strip() for line in win32evtlogutil.SafeFormatMessage(ev, 'Security').split(chr(10)) if line.strip())[:300]
                except: msg = f'Event {eid}'
                level = 'critical' if eid in {4648,4703,4704} else 'warn' if eid == 4625 else 'info'
                events.append({'id': eid, 'level': level, 'time': t, 'msg': msg})
        win32evtlog.CloseEventLog(hand)
        return events
    except: return []

def collect():
    ip, mac = get_primary_ip_mac()
    try: users = psutil.users(); user, ss = (users[0].name, int(users[0].started)) if users else (os.environ.get('USERNAME','?'), int(time.time()))
    except: user, ss = os.environ.get('USERNAME','?'), int(time.time())
    return {
        'hostname': socket.gethostname(), 'ip': ip, 'mac': mac, 'os': get_os_version(),
        'domain': get_domain(), 'user': user, 'session_start': ss,
        'cpu': int(psutil.cpu_percent(interval=1)), 'ram': int(psutil.virtual_memory().percent),
        'disk': int(psutil.disk_usage('C:\\').percent),
        'processes': get_processes(), 'events': get_events(),
    }

def report(url, key, payload):
    r = requests.post(f'{url}/api/workstations/report', json=payload, headers={'X-Agent-Key': key}, timeout=10)
    r.raise_for_status(); return r.json()

def agent_loop(url, key, stop_event=None):
    log.info(f'Reporting to {url} every {INTERVAL}s')
    while not (stop_event and stop_event.is_set()):
        try:
            resp = report(url, key, collect())
            log.info(f'Reported {socket.gethostname()} — {resp.get("status","?")}')
        except Exception as e: log.error(f'Report failed: {e}')
        for _ in range(INTERVAL):
            if stop_event and stop_event.is_set(): break
            time.sleep(1)

# ── Windows Service ───────────────────────────────────────
try:
    import win32serviceutil, win32service, win32event, servicemanager
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
            os.makedirs(CONFIG_DIR, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE)
            fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
            logging.getLogger().addHandler(fh)
            cfg = load_config()
            if not cfg.get('url') or not cfg.get('key'):
                log.error(f'No config at {CONFIG_FILE}'); return
            stop = threading.Event()
            def w(): win32event.WaitForSingleObject(self.stop_event, win32event.INFINITE); stop.set()
            threading.Thread(target=w, daemon=True).start()
            agent_loop(cfg['url'], cfg['key'], stop)
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# ── GUI Installer ─────────────────────────────────────────
def gui_installer():
    import tkinter as tk
    from tkinter import messagebox

    cfg = load_config()

    def is_admin():
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False

    def svc_state():
        r = subprocess.run(['sc', 'query', SERVICE_NAME], capture_output=True, text=True)
        if r.returncode != 0: return 'NOT INSTALLED'
        if 'RUNNING' in r.stdout: return 'RUNNING'
        if 'STOPPED' in r.stdout: return 'STOPPED'
        return 'UNKNOWN'

    def refresh_status():
        s = svc_state()
        status_var.set(f'Service: {s}')
        btn_install.config(state='normal' if s == 'NOT INSTALLED' else 'disabled')
        btn_start.config(state='normal' if s == 'STOPPED' else 'disabled')
        btn_stop.config(state='normal' if s == 'RUNNING' else 'disabled')
        btn_remove.config(state='normal' if s in ('STOPPED', 'NOT INSTALLED') else 'disabled')

    def do_save():
        u, k = url_var.get().strip().rstrip('/'), key_var.get().strip()
        if not u or not k:
            messagebox.showerror('Error', 'URL and Key are required'); return
        save_config({'url': u, 'key': k})
        try:
            r = requests.get(f'{u}/api/health', timeout=5)
            if r.status_code == 200:
                messagebox.showinfo('Saved', f'Config saved.\nConnection test: OK')
            else:
                messagebox.showwarning('Saved', f'Config saved.\nConnection test: HTTP {r.status_code}')
        except Exception as e:
            messagebox.showwarning('Saved', f'Config saved.\nConnection test: FAILED\n{e}')

    def do_install():
        src = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        os.makedirs(PROGRAM_DIR, exist_ok=True)
        if os.path.normpath(src) != os.path.normpath(INSTALL_EXE):
            shutil.copy2(src, INSTALL_EXE)
        try:
            subprocess.run(['sc', 'create', SERVICE_NAME, f'binPath={INSTALL_EXE} --run-service',
                            f'DisplayName={SERVICE_DISPLAY}', 'start=auto'], check=True,
                           capture_output=True, text=True)
            subprocess.run(['sc', 'description', SERVICE_NAME, SERVICE_DESC], capture_output=True)
            subprocess.run(['sc', 'failure', SERVICE_NAME, 'reset=86400',
                            'actions=restart/10000/restart/30000/restart/60000'], capture_output=True)
            messagebox.showinfo('Installed', 'Service installed. Click Start.')
        except Exception as e:
            messagebox.showerror('Error', f'Install failed:\n{e}')
        refresh_status()

    def do_start():
        try:
            subprocess.run(['sc', 'start', SERVICE_NAME], check=True, capture_output=True, text=True)
        except Exception as e:
            messagebox.showerror('Error', f'Start failed:\n{e}')
        root.after(2000, refresh_status)

    def do_stop():
        try:
            subprocess.run(['sc', 'stop', SERVICE_NAME], check=True, capture_output=True, text=True)
        except Exception as e:
            messagebox.showerror('Error', f'Stop failed:\n{e}')
        root.after(2000, refresh_status)

    def do_remove():
        subprocess.run(['sc', 'stop', SERVICE_NAME], capture_output=True)
        time.sleep(1)
        try:
            subprocess.run(['sc', 'delete', SERVICE_NAME], check=True, capture_output=True, text=True)
            messagebox.showinfo('Removed', 'Service removed.')
        except Exception as e:
            messagebox.showerror('Error', f'Remove failed:\n{e}')
        refresh_status()

    root = tk.Tk()
    root.title('SecNet Agent Setup')
    root.geometry('420x340')
    root.resizable(False, False)

    if not is_admin():
        messagebox.showwarning('Admin Required', 'Please right-click the exe and select\n"Run as administrator"')
        root.destroy(); return

    tk.Label(root, text='SecNet Agent', font=('Segoe UI', 14, 'bold')).pack(pady=(12, 4))
    tk.Label(root, text=get_os_version(), fg='gray').pack()

    frame = tk.Frame(root)
    frame.pack(pady=10, padx=20, fill='x')

    tk.Label(frame, text='Dashboard URL:').grid(row=0, column=0, sticky='w', pady=2)
    url_var = tk.StringVar(value=cfg.get('url', ''))
    tk.Entry(frame, textvariable=url_var, width=38).grid(row=0, column=1, pady=2, padx=(5,0))

    tk.Label(frame, text='Agent Key:').grid(row=1, column=0, sticky='w', pady=2)
    key_var = tk.StringVar(value=cfg.get('key', ''))
    tk.Entry(frame, textvariable=key_var, width=38, show='*').grid(row=1, column=1, pady=2, padx=(5,0))

    tk.Button(root, text='Save Config & Test Connection', command=do_save, width=32).pack(pady=(5, 10))

    status_var = tk.StringVar(value='Service: ...')
    tk.Label(root, textvariable=status_var, font=('Segoe UI', 10, 'bold')).pack()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=8)
    btn_install = tk.Button(btn_frame, text='Install', command=do_install, width=10)
    btn_install.grid(row=0, column=0, padx=4)
    btn_start = tk.Button(btn_frame, text='Start', command=do_start, width=10)
    btn_start.grid(row=0, column=1, padx=4)
    btn_stop = tk.Button(btn_frame, text='Stop', command=do_stop, width=10)
    btn_stop.grid(row=0, column=2, padx=4)
    btn_remove = tk.Button(btn_frame, text='Remove', command=do_remove, width=10)
    btn_remove.grid(row=0, column=3, padx=4)

    refresh_status()
    root.mainloop()

# ── Entry point ───────────────────────────────────────────
def main():
    if '--run-service' in sys.argv:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SecNetService)
        servicemanager.StartServiceCtrlDispatcher()
        return

    # CLI mode if any arguments given
    if len(sys.argv) > 1 and sys.argv[1] != '--run-service':
        import argparse
        parser = argparse.ArgumentParser(prog='secnet-agent')
        sub = parser.add_subparsers(dest='command')
        p = sub.add_parser('setup'); p.add_argument('--url'); p.add_argument('--key')
        sub.add_parser('install'); sub.add_parser('remove')
        sub.add_parser('start'); sub.add_parser('stop'); sub.add_parser('status')
        p = sub.add_parser('run'); p.add_argument('--url', default=''); p.add_argument('--key', default='')
        args = parser.parse_args()
        if args.command == 'run':
            cfg = load_config()
            agent_loop(args.url or cfg.get('url',''), args.key or cfg.get('key',''))
        elif args.command == 'setup':
            save_config({'url': args.url.rstrip('/'), 'key': args.key}); print('Saved')
        elif args.command == 'install':
            src = sys.executable if getattr(sys, 'frozen', False) else __file__
            os.makedirs(PROGRAM_DIR, exist_ok=True); shutil.copy2(src, INSTALL_EXE)
            subprocess.run(['sc','create',SERVICE_NAME,f'binPath={INSTALL_EXE} --run-service',f'DisplayName={SERVICE_DISPLAY}','start=auto'], check=True)
            subprocess.run(['sc','description',SERVICE_NAME,SERVICE_DESC], capture_output=True)
            subprocess.run(['sc','failure',SERVICE_NAME,'reset=86400','actions=restart/10000/restart/30000/restart/60000'], capture_output=True)
            print('Installed')
        elif args.command == 'start': subprocess.run(['sc','start',SERVICE_NAME], check=True)
        elif args.command == 'stop': subprocess.run(['sc','stop',SERVICE_NAME], check=True)
        elif args.command == 'remove':
            subprocess.run(['sc','stop',SERVICE_NAME], capture_output=True); time.sleep(1)
            subprocess.run(['sc','delete',SERVICE_NAME], check=True); print('Removed')
        elif args.command == 'status':
            r = subprocess.run(['sc','query',SERVICE_NAME], capture_output=True, text=True)
            print(r.stdout if r.returncode == 0 else 'NOT INSTALLED')
        return

    # No arguments = double-click = GUI
    gui_installer()

if __name__ == '__main__':
    main()
