import React, { useState } from 'react'

const MOCK_WORKSTATIONS = [
  {
    id: 'WS-MKTING-01',
    hostname: 'DESKTOP-MKTING01',
    status: 'healthy',
    user: 'sarah.johnson',
    domain: 'CORP',
    session_start: Date.now() - 3 * 3600000 - 22 * 60000,
    os: 'Windows 11 Pro 23H2',
    cpu: 18,
    ram: 42,
    disk: 61,
    ip: '192.168.1.112',
    mac: 'B4:2E:99:14:3A:1F',
    last_seen: Date.now() - 45000,
    processes: [
      { name: 'Teams.exe', pid: 4812, cpu: 3.2, ram: 312, flags: [] },
      { name: 'WINWORD.EXE', pid: 9120, cpu: 0.8, ram: 145, flags: [] },
      { name: 'chrome.exe', pid: 3344, cpu: 4.1, ram: 480, flags: [] },
      { name: 'explorer.exe', pid: 1024, cpu: 0.1, ram: 55, flags: [] },
    ],
    events: [
      { id: 4624, level: 'info', time: '09:12:44', msg: 'Account logon — sarah.johnson (Interactive)' },
      { id: 4688, level: 'info', time: '09:13:02', msg: 'New process: Teams.exe (PID 4812)' },
      { id: 4688, level: 'info', time: '09:15:17', msg: 'New process: WINWORD.EXE (PID 9120)' },
      { id: 7045, level: 'info', time: '08:01:05', msg: 'Service installed: Windows Update' },
    ],
    alerts: [],
  },
  {
    id: 'WS-EXEC-CFO',
    hostname: 'LAPTOP-EXEC-CFO',
    status: 'suspicious',
    user: 'john.hargrove',
    domain: 'CORP',
    session_start: Date.now() - 1 * 3600000 - 5 * 60000,
    os: 'Windows 11 Pro 23H2',
    cpu: 67,
    ram: 78,
    disk: 44,
    ip: '192.168.1.88',
    mac: 'A0:CE:C8:D7:22:4B',
    last_seen: Date.now() - 12000,
    processes: [
      { name: 'chrome.exe', pid: 2200, cpu: 12.4, ram: 620, flags: [] },
      { name: 'outlook.exe', pid: 5544, cpu: 1.2, ram: 210, flags: [] },
      { name: 'tor.exe', pid: 8831, cpu: 22.1, ram: 88, flags: ['suspicious', 'network'] },
      { name: 'powershell.exe', pid: 9912, cpu: 8.4, ram: 64, flags: ['suspicious'] },
    ],
    events: [
      { id: 4624, level: 'info', time: '11:47:03', msg: 'Account logon — john.hargrove (Interactive)' },
      { id: 4688, level: 'warn', time: '11:51:20', msg: 'New process: tor.exe (PID 8831) — unusual executable' },
      { id: 4688, level: 'warn', time: '11:52:44', msg: 'New process: powershell.exe with -EncodedCommand flag' },
      { id: 5156, level: 'warn', time: '11:53:01', msg: 'Outbound connection on port 9001 (TOR relay)' },
    ],
    alerts: ['TOR process detected', 'Encoded PowerShell execution'],
  },
  {
    id: 'WS-DEV-04',
    hostname: 'WORKSTATION-DEV04',
    status: 'healthy',
    user: 'mike.tran',
    domain: 'CORP',
    session_start: Date.now() - 6 * 3600000 - 44 * 60000,
    os: 'Windows 11 Pro 23H2',
    cpu: 34,
    ram: 55,
    disk: 38,
    ip: '192.168.1.74',
    mac: '3C:7C:3F:AB:12:88',
    last_seen: Date.now() - 8000,
    processes: [
      { name: 'Code.exe', pid: 7210, cpu: 8.1, ram: 520, flags: [] },
      { name: 'node.exe', pid: 11034, cpu: 12.3, ram: 288, flags: [] },
      { name: 'docker.exe', pid: 3341, cpu: 6.2, ram: 180, flags: [] },
      { name: 'git.exe', pid: 14420, cpu: 0.2, ram: 22, flags: [] },
    ],
    events: [
      { id: 4624, level: 'info', time: '06:02:11', msg: 'Account logon — mike.tran (Interactive)' },
      { id: 4688, level: 'info', time: '06:03:44', msg: 'New process: Code.exe' },
      { id: 4688, level: 'info', time: '06:05:02', msg: 'New process: docker.exe' },
      { id: 4688, level: 'info', time: '10:31:19', msg: 'New process: node.exe (npm build)' },
    ],
    alerts: [],
  },
  {
    id: 'WS-FINANCE-02',
    hostname: 'DESKTOP-FINANCE02',
    status: 'compromised',
    user: 'linda.chen',
    domain: 'CORP',
    session_start: Date.now() - 2 * 3600000 - 18 * 60000,
    os: 'Windows 10 Pro 22H2',
    cpu: 91,
    ram: 88,
    disk: 72,
    ip: '192.168.1.103',
    mac: 'D8:BB:C1:55:7E:2A',
    last_seen: Date.now() - 3000,
    processes: [
      { name: 'svchost.exe', pid: 1188, cpu: 0.4, ram: 44, flags: [] },
      { name: 'lsass.exe', pid: 688, cpu: 31.2, ram: 312, flags: ['critical', 'suspicious'] },
      { name: 'rundll32.exe', pid: 14882, cpu: 28.4, ram: 122, flags: ['suspicious', 'injection'] },
      { name: 'cmd.exe', pid: 15001, cpu: 0.8, ram: 18, flags: ['suspicious'] },
      { name: 'net.exe', pid: 15044, cpu: 2.1, ram: 12, flags: ['suspicious', 'recon'] },
    ],
    events: [
      { id: 4624, level: 'info', time: '10:34:07', msg: 'Account logon — linda.chen (Interactive)' },
      { id: 4648, level: 'critical', time: '10:41:22', msg: 'Explicit credential logon attempt to 192.168.1.201' },
      { id: 4688, level: 'critical', time: '10:41:55', msg: 'Suspicious process: rundll32.exe injecting into lsass.exe' },
      { id: 4703, level: 'critical', time: '10:42:11', msg: 'Privilege escalation — token manipulation detected' },
      { id: 4776, level: 'critical', time: '10:42:33', msg: 'Credential validation attempt — CORP\\Administrator' },
    ],
    alerts: ['LSASS memory access (credential dump)', 'Lateral movement to .201', 'Privilege escalation', 'Admin credential probe'],
  },
  {
    id: 'WS-RECEPTION',
    hostname: 'PC-RECEPTION01',
    status: 'warning',
    user: 'guest.kiosk',
    domain: 'CORP',
    session_start: Date.now() - 14 * 3600000 - 37 * 60000,
    os: 'Windows 10 Pro 21H2',
    cpu: 2,
    ram: 19,
    disk: 55,
    ip: '192.168.1.145',
    mac: '00:11:32:4F:9B:CC',
    last_seen: Date.now() - 90000,
    processes: [
      { name: 'explorer.exe', pid: 2048, cpu: 0.1, ram: 48, flags: [] },
      { name: 'chrome.exe', pid: 4400, cpu: 0.8, ram: 210, flags: [] },
    ],
    events: [
      { id: 4624, level: 'info', time: '08:55:02', msg: 'Account logon — guest.kiosk (Interactive)' },
      { id: 4800, level: 'warn', time: '09:22:14', msg: 'Workstation locked (screensaver)' },
      { id: 4801, level: 'warn', time: '11:44:31', msg: 'Workstation unlocked — no re-authentication recorded' },
      { id: 4800, level: 'info', time: '11:49:02', msg: 'Workstation locked again' },
    ],
    alerts: ['Session active 14h 37m — unattended kiosk session'],
  },
  {
    id: 'WS-REMOTE-VPN',
    hostname: 'LAPTOP-REMOTE-VPN',
    status: 'suspicious',
    user: 'alex.woods',
    domain: 'CORP',
    session_start: Date.now() - 0.5 * 3600000 - 12 * 60000,
    os: 'Windows 11 Pro 23H2',
    cpu: 44,
    ram: 61,
    disk: 49,
    ip: '192.168.4.12',
    mac: '8C:85:90:44:EE:01',
    last_seen: Date.now() - 5000,
    processes: [
      { name: 'mstsc.exe', pid: 7730, cpu: 8.2, ram: 155, flags: ['network'] },
      { name: 'wermgr.exe', pid: 9901, cpu: 14.3, ram: 44, flags: ['suspicious'] },
      { name: 'cmd.exe', pid: 10220, cpu: 2.1, ram: 16, flags: ['suspicious'] },
      { name: 'net.exe', pid: 10315, cpu: 0.8, ram: 12, flags: ['suspicious', 'recon'] },
    ],
    events: [
      { id: 4625, level: 'warn', time: '12:18:04', msg: '3x failed logon for CORP\\admin (RDP)' },
      { id: 4625, level: 'warn', time: '12:18:09', msg: '3x failed logon for CORP\\administrator (RDP)' },
      { id: 4624, level: 'info', time: '12:21:03', msg: 'Account logon — alex.woods (VPN/Remote)' },
      { id: 4688, level: 'warn', time: '12:22:44', msg: 'RDP session opened to 192.168.1.103' },
      { id: 4688, level: 'warn', time: '12:24:11', msg: 'net.exe — domain enumeration commands detected' },
    ],
    alerts: ['Admin credential brute-force (pre-logon)', 'RDP hop to DESKTOP-FINANCE02', 'Domain recon via net.exe'],
  },
]

function formatSessionTime(start) {
  const ms = Date.now() - start
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function formatLastSeen(ts) {
  const s = Math.floor((Date.now() - ts) / 1000)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  return `${Math.floor(s / 3600)}h ago`
}

function UsageBar({ value, warn = 70, danger = 90, label }) {
  const color = value >= danger ? 'var(--red)' : value >= warn ? 'var(--amber)' : 'var(--green)'
  return (
    <div className="ws-bar-wrap">
      <span className="ws-bar-label">{label}</span>
      <div className="ws-bar-track">
        <div className="ws-bar-fill" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="ws-bar-pct" style={{ color }}>{value}%</span>
    </div>
  )
}

function EventRow({ ev }) {
  const levelColor = ev.level === 'critical' ? 'var(--red)' : ev.level === 'warn' ? 'var(--amber)' : 'var(--text-muted)'
  return (
    <div className="ws-event-row">
      <span className="ws-event-time mono">{ev.time}</span>
      <span className="ws-event-id mono" style={{ color: levelColor }}>EVT-{ev.id}</span>
      <span className="ws-event-msg">{ev.msg}</span>
    </div>
  )
}

function ProcessRow({ proc }) {
  const isSuspicious = proc.flags.includes('suspicious') || proc.flags.includes('critical')
  const isInjection = proc.flags.includes('injection')
  const flagColor = isInjection ? 'var(--red)' : isSuspicious ? 'var(--amber)' : 'var(--text-muted)'
  return (
    <div className="ws-proc-row" style={{ background: isSuspicious ? 'rgba(255,71,87,0.05)' : 'transparent' }}>
      <span className="ws-proc-name mono" style={{ color: isSuspicious ? flagColor : 'var(--text)' }}>{proc.name}</span>
      <span className="ws-proc-pid mono text-muted">{proc.pid}</span>
      <span className="ws-proc-cpu" style={{ color: proc.cpu > 20 ? 'var(--amber)' : 'var(--text-muted)' }}>{proc.cpu.toFixed(1)}%</span>
      <span className="ws-proc-ram text-muted">{proc.ram} MB</span>
      <span className="ws-proc-flags">
        {proc.flags.map(f => (
          <span key={f} className="ws-flag" style={{ borderColor: flagColor, color: flagColor }}>{f}</span>
        ))}
      </span>
    </div>
  )
}

function WorkstationCard({ ws }) {
  const [expanded, setExpanded] = useState(false)

  const statusConfig = {
    healthy: { color: 'var(--green)', icon: '', label: 'Healthy' },
    warning: { color: 'var(--amber)', icon: '', label: 'Warning' },
    suspicious: { color: 'var(--amber)', icon: '', label: 'Suspicious' },
    compromised: { color: 'var(--red)', icon: '', label: 'COMPROMISED' },
  }
  const sc = statusConfig[ws.status] || statusConfig.healthy

  return (
    <div className="ws-card" style={{ borderColor: ws.alerts.length > 0 ? sc.color : 'var(--border)' }}>
      <div className="ws-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="ws-card-title">
          <span className="ws-hostname mono">{ws.hostname}</span>
          <span className="ws-badge" style={{ background: `${sc.color}22`, color: sc.color, border: `1px solid ${sc.color}44` }}>{sc.label}</span>
        </div>
        <div className="ws-card-meta">
          <span className="ws-user">{ws.user}</span>
          <span className="ws-session text-muted">Session: {formatSessionTime(ws.session_start)}</span>
          <span className="ws-lastseen text-muted">Seen: {formatLastSeen(ws.last_seen)}</span>
          <span className="ws-ip mono text-muted">{ws.ip}</span>
          <span className="ws-expand-icon">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {ws.alerts.length > 0 && (
        <div className="ws-alert-bar">
          {ws.alerts.map((a, i) => (
            <span key={i} className="ws-alert-chip">{a}</span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="ws-card-body">
          <div className="ws-detail-row">
            <div className="ws-col">
              <div className="ws-section-label">System</div>
              <div className="ws-detail-info">
                <div><span className="text-muted">OS:</span> {ws.os}</div>
                <div><span className="text-muted">Domain:</span> {ws.domain}</div>
                <div><span className="text-muted">MAC:</span> <span className="mono">{ws.mac}</span></div>
              </div>
              <div className="ws-bars">
                <UsageBar value={ws.cpu} label="CPU" />
                <UsageBar value={ws.ram} label="RAM" warn={75} danger={90} />
                <UsageBar value={ws.disk} label="Disk" warn={80} danger={95} />
              </div>
            </div>

            <div className="ws-col">
              <div className="ws-section-label">Processes ({ws.processes.length})</div>
              <div className="ws-proc-table">
                <div className="ws-proc-header">
                  <span>Name</span><span>PID</span><span>CPU</span><span>RAM</span><span>Flags</span>
                </div>
                {ws.processes.map(p => <ProcessRow key={p.pid} proc={p} />)}
              </div>
            </div>
          </div>

          <div className="ws-section-label" style={{ marginTop: '12px' }}>Event Log</div>
          <div className="ws-event-log">
            {ws.events.map((ev, i) => <EventRow key={i} ev={ev} />)}
          </div>
        </div>
      )}
    </div>
  )
}

export default function Workstations() {
  const [filter, setFilter] = useState('all')

  const counts = {
    all: MOCK_WORKSTATIONS.length,
    healthy: MOCK_WORKSTATIONS.filter(w => w.status === 'healthy').length,
    suspicious: MOCK_WORKSTATIONS.filter(w => w.status === 'suspicious' || w.status === 'warning').length,
    compromised: MOCK_WORKSTATIONS.filter(w => w.status === 'compromised').length,
  }

  let filtered
  if (filter === 'all') {
    filtered = MOCK_WORKSTATIONS
  } else if (filter === 'suspicious') {
    filtered = MOCK_WORKSTATIONS.filter(w => w.status === 'suspicious' || w.status === 'warning')
  } else {
    filtered = MOCK_WORKSTATIONS.filter(w => w.status === filter)
  }

  return (
    <div className="workstations">
      <div className="ws-header">
        <h3>Windows Workstations — At a Glance</h3>
        <span className="text-muted ws-note">Mock data — wire to WinRM/agent for live feed</span>
      </div>

      <div className="ws-filter-bar">
        {[
          { key: 'all', label: `All (${counts.all})`, color: 'var(--blue)' },
          { key: 'healthy', label: `Healthy (${counts.healthy})`, color: 'var(--green)' },
          { key: 'suspicious', label: `Suspicious (${counts.suspicious})`, color: 'var(--amber)' },
          { key: 'compromised', label: `Compromised (${counts.compromised})`, color: 'var(--red)' },
        ].map(f => (
          <button
            key={f.key}
            className={`ws-filter-btn ${filter === f.key ? 'ws-filter-active' : ''}`}
            style={filter === f.key ? { borderColor: f.color, color: f.color } : {}}
            onClick={() => setFilter(f.key)}
          >{f.label}</button>
        ))}
      </div>

      <div className="ws-list">
        {filtered.map(ws => <WorkstationCard key={ws.id} ws={ws} />)}
      </div>
    </div>
  )
}
