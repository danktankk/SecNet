import React, { useState } from 'react'
import { useApi } from '../hooks/useApi'

function formatSessionTime(start) {
  const ms = Date.now() - start * 1000
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function formatLastSeen(ts) {
  const s = Math.floor((Date.now() - ts * 1000) / 1000)
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
    healthy:    { color: 'var(--green)', label: 'Healthy' },
    warning:    { color: 'var(--amber)', label: 'Warning' },
    suspicious: { color: 'var(--amber)', label: 'Suspicious' },
    compromised:{ color: 'var(--red)',   label: 'COMPROMISED' },
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
          {ws.alerts.map((a, i) => <span key={i} className="ws-alert-chip">{a}</span>)}
        </div>
      )}

      <div className="ws-system-bar">
        <div className="ws-detail-info-inline">
          <span><span className="text-muted">OS:</span> {ws.os}</span>
          <span className="ws-sys-sep">·</span>
          <span><span className="text-muted">Domain:</span> {ws.domain || '—'}</span>
          <span className="ws-sys-sep">·</span>
          <span><span className="text-muted">MAC:</span> <span className="mono">{ws.mac}</span></span>
        </div>
        <div className="ws-bars-inline">
          <UsageBar value={ws.cpu} label="CPU" />
          <UsageBar value={ws.ram} label="RAM" warn={75} danger={90} />
          <UsageBar value={ws.disk} label="Disk" warn={80} danger={95} />
        </div>
      </div>

      {expanded && (
        <div className="ws-card-body">
          <div className="ws-detail-row">
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
            {ws.events.length > 0
              ? ws.events.map((ev, i) => <EventRow key={i} ev={ev} />)
              : <div className="text-muted" style={{padding:'8px'}}>No security events captured yet.</div>
            }
          </div>
        </div>
      )}
    </div>
  )
}

export default function Workstations() {
  const { data: workstations } = useApi('/api/workstations', 30000)
  const [filter, setFilter] = useState('all')
  const ws = workstations || []

  const counts = {
    all: ws.length,
    healthy: ws.filter(w => w.status === 'healthy').length,
    suspicious: ws.filter(w => w.status === 'suspicious' || w.status === 'warning').length,
    compromised: ws.filter(w => w.status === 'compromised').length,
  }
  const filtered = filter === 'all' ? ws
    : filter === 'suspicious' ? ws.filter(w => w.status === 'suspicious' || w.status === 'warning')
    : ws.filter(w => w.status === filter)

  if (ws.length === 0) {
    return (
      <div className="workstations">
        <div className="ws-header">
          <h3>Windows Workstations</h3>
        </div>
        <div className="panel" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
          No workstations reporting yet.<br /><br />
          Run the agent on your Windows machine:<br />
          <code style={{ display: 'block', marginTop: '12px', fontSize: '0.85rem' }}>
            pip install psutil requests<br />
            python secnet-agent.py --url http://SECNET_HOST:8088 --key YOUR_AGENT_KEY
          </code>
        </div>
      </div>
    )
  }

  return (
    <div className="workstations">
      <div className="ws-header">
        <h3>Windows Workstations — Live</h3>
      </div>
      <div className="ws-filter-bar">
        {[
          { key: 'all',        label: `All (${counts.all})`,               color: 'var(--blue)'  },
          { key: 'healthy',    label: `Healthy (${counts.healthy})`,        color: 'var(--green)' },
          { key: 'suspicious', label: `Suspicious (${counts.suspicious})`,  color: 'var(--amber)' },
          { key: 'compromised',label: `Compromised (${counts.compromised})`,color: 'var(--red)'   },
        ].map(f => (
          <button key={f.key}
            className={`ws-filter-btn ${filter === f.key ? 'ws-filter-active' : ''}`}
            style={filter === f.key ? { borderColor: f.color, color: f.color } : {}}
            onClick={() => setFilter(f.key)}
          >{f.label}</button>
        ))}
      </div>
      <div className="ws-list">
        {filtered.map(w => <WorkstationCard key={w.id} ws={w} />)}
      </div>
    </div>
  )
}
