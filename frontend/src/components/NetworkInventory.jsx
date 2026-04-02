import React, { useState } from 'react'
import { useApi } from '../hooks/useApi'
import GateUnlock from './GateUnlock'
import GateSessionBar from './GateSessionBar'
import { fmtMem } from '../utils/format'
import { gateIsValid, TOKEN_KEY } from '../utils/gate'

const severityColor = (sev) => sev === 'safe' ? 'var(--green)' : sev === 'danger' ? 'var(--red)' : 'var(--amber)'

function PortResults({ ip }) {
  const [scanning, setScanning] = useState(false)
  const [results, setResults] = useState(null)

  const scan = async () => {
    setScanning(true)
    const token = sessionStorage.getItem(TOKEN_KEY) || ''
    try {
      const r = await fetch(`/api/network/scan/${ip}`, { method: 'POST', headers: { 'X-Gate-Token': token } })
      setResults(await r.json())
    } catch { setResults({ error: 'Scan failed' }) }
    setScanning(false)
  }

  return (
    <div className="port-results">
      <button className="scan-btn" onClick={scan} disabled={scanning}>
        {scanning ? 'Scanning...' : 'Scan Ports'}
      </button>
      {results && results.ports && (
        <div className="port-list">
          {results.ports.length === 0 && <div className="text-muted">No open ports found</div>}
          {results.ports.map(p => (
            <span key={p.port} className="port-tag" style={{ borderColor: severityColor(p.severity), color: severityColor(p.severity) }}>
              {p.port}/{p.proto} {p.service} ({p.state})
            </span>
          ))}
          {results.error && <div style={{ color: 'var(--red)' }}>{results.error}</div>}
        </div>
      )}
    </div>
  )
}

function ManualScan() {
  const [ip, setIp] = useState('')
  const [scanning, setScanning] = useState(false)
  const [results, setResults] = useState(null)

  const scan = async () => {
    if (!ip.trim()) return
    setScanning(true)
    const token = sessionStorage.getItem(TOKEN_KEY) || ''
    try {
      const r = await fetch(`/api/network/scan/${ip.trim()}`, { method: 'POST', headers: { 'X-Gate-Token': token } })
      setResults(await r.json())
    } catch { setResults({ error: 'Scan failed' }) }
    setScanning(false)
  }

  return (
    <div className="port-results">
      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
        <input
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text)', padding: '4px 8px', borderRadius: '4px', fontSize: '12px', width: '150px' }}
          placeholder="Enter IP to scan"
          value={ip}
          onChange={e => setIp(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && scan()}
        />
        <button className="scan-btn" onClick={scan} disabled={scanning || !ip.trim()}>
          {scanning ? 'Scanning...' : 'Scan'}
        </button>
      </div>
      {results?.ports && (
        <div className="port-list">
          {results.ports.length === 0 && <span className="text-muted">No open ports</span>}
          {results.ports.map(p => (
            <span key={p.port} className="port-tag" style={{ borderColor: severityColor(p.severity), color: severityColor(p.severity) }}>
              {p.port}/{p.proto} {p.service}
            </span>
          ))}
          {results.error && <span style={{ color: 'var(--red)', fontSize: '12px' }}>{results.error}</span>}
        </div>
      )}
    </div>
  )
}

function InfraBar({ value, warn = 60, danger = 85, label }) {
  const pct = Math.min(100, value)
  const color = pct >= danger ? 'var(--red)' : pct >= warn ? 'var(--amber)' : 'var(--green)'
  return (
    <div className="infra-bar-wrap">
      <span className="infra-bar-label">{label}</span>
      <div className="infra-bar-track">
        <div className="infra-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="infra-bar-pct" style={{ color }}>{value}%</span>
    </div>
  )
}

function GuestCard({ guest, unlocked }) {
  const [expanded, setExpanded] = useState(false)
  const statusColor = guest.status === 'running' ? 'var(--green)' : 'var(--text-muted)'
  const blurClass = unlocked ? '' : 'blurred-text'
  const typeBadgeColor = guest.type === 'qemu' ? 'var(--blue)' : 'var(--amber)'

  return (
    <div className="infra-card" style={{ borderColor: guest.status === 'running' ? 'var(--border)' : 'rgba(48,54,61,0.5)' }}>
      <div className="infra-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="infra-card-title">
          <span className="infra-status-dot" style={{ background: statusColor, boxShadow: `0 0 6px ${statusColor}` }} />
          <span className={`infra-name mono ${blurClass}`}>
            {unlocked ? (guest.name || `VM ${guest.vmid}`) : '----------'}
          </span>
          <span className="infra-type-badge" style={{ background: `${typeBadgeColor}22`, color: typeBadgeColor, border: `1px solid ${typeBadgeColor}44` }}>
            {guest.type === 'qemu' ? 'VM' : 'LXC'}
          </span>
        </div>
        <div className="infra-card-meta">
          {guest.ip && <span className={`mono ${blurClass}`} style={{ fontSize: '0.75rem' }}>{unlocked ? guest.ip : '---.---.---.---'}</span>}
          {guest.status === 'running' && (
            <>
              <span className="text-muted" style={{ fontSize: '0.73rem' }}>CPU {guest.cpu}%</span>
              <span className="text-muted" style={{ fontSize: '0.73rem' }}>RAM {guest.mem_pct}%</span>
            </>
          )}
          {guest.status !== 'running' && <span className="text-muted" style={{ fontSize: '0.73rem' }}>{guest.status}</span>}
          <span className="infra-expand-icon">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>

      {expanded && (
        <div className="infra-card-body">
          {guest.status === 'running' ? (
            <>
              <div className="infra-detail-grid">
                <div className="infra-detail-col">
                  <div className="infra-section-label">System</div>
                  <div className="infra-detail-info">
                    <div><span className="text-muted">ID:</span> {guest.vmid}</div>
                    <div><span className="text-muted">Type:</span> {guest.type === 'qemu' ? 'Virtual Machine' : 'LXC Container'}</div>
                    <div><span className="text-muted">Status:</span> <span style={{ color: statusColor }}>{guest.status}</span></div>
                    <div><span className="text-muted">RAM:</span> {fmtMem(guest.mem_used)} / {fmtMem(guest.mem_total)}</div>
                  </div>
                </div>
                <div className="infra-detail-col">
                  <div className="infra-section-label">Telemetry</div>
                  <div className="infra-bars">
                    <InfraBar value={guest.cpu} label="CPU" />
                    <InfraBar value={guest.mem_pct} label="RAM" warn={75} danger={90} />
                  </div>
                </div>
              </div>
              {unlocked && guest.ip && <PortResults ip={guest.ip} />}
              {unlocked && !guest.ip && <ManualScan />}
            </>
          ) : (
            <div className="text-muted" style={{ padding: '8px 0', fontSize: '12px' }}>Guest is stopped</div>
          )}
        </div>
      )}
    </div>
  )
}

function NodeCard({ node, unlocked }) {
  const [expanded, setExpanded] = useState(false)
  const blurClass = unlocked ? '' : 'blurred-text'
  const hasError = !!node.error
  const statusColor = hasError ? 'var(--red)' : 'var(--green)'
  const guestCount = node.guests?.length || 0
  const runningCount = (node.guests || []).filter(g => g.status === 'running').length

  return (
    <div className="infra-card infra-node-card" style={{ borderColor: hasError ? 'var(--red)' : 'var(--border)' }}>
      <div className="infra-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="infra-card-title">
          <span className="infra-status-dot" style={{ background: statusColor, boxShadow: `0 0 6px ${statusColor}` }} />
          <span className={`infra-node-name ${blurClass}`}>
            {unlocked ? node.node : '------'}
          </span>
        </div>
        <div className="infra-card-meta">
          {hasError ? (
            <span style={{ color: 'var(--red)', fontSize: '0.78rem' }}>Error</span>
          ) : (
            <>
              <span className="text-muted" style={{ fontSize: '0.73rem' }}>CPU {node.cpu_pct}%</span>
              <span className="text-muted" style={{ fontSize: '0.73rem' }}>RAM {node.mem_pct}%</span>
              <span className="text-muted" style={{ fontSize: '0.73rem' }}>{runningCount}/{guestCount} guests</span>
            </>
          )}
          <span className="infra-expand-icon">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>

      {expanded && (
        <div className="infra-card-body">
          {hasError ? (
            <div style={{ color: 'var(--red)', fontSize: '0.82rem', padding: '8px 0' }}>{node.error}</div>
          ) : (
            <>
              <div className="infra-node-metrics">
                <div className="infra-detail-col">
                  <div className="infra-section-label">Node Metrics</div>
                  <div className="infra-bars">
                    <InfraBar value={node.cpu_pct} label="CPU" />
                    <InfraBar value={node.mem_pct} label="RAM" warn={75} danger={90} />
                  </div>
                  <div className="infra-detail-info" style={{ marginTop: 8 }}>
                    <div><span className="text-muted">RAM:</span> {fmtMem(node.mem_used)} / {fmtMem(node.mem_total)}</div>
                    <div><span className="text-muted">Guests:</span> {runningCount} running / {guestCount} total</div>
                  </div>
                </div>
                {unlocked && (
                  <div className="infra-detail-col">
                    <div className="infra-section-label">Node Port Scan</div>
                    <PortResults ip={node.url?.replace('https://', '').replace(':8006', '')} />
                  </div>
                )}
              </div>

              <div className="infra-section-label" style={{ marginTop: 12 }}>Guests ({guestCount})</div>
              <div className="infra-guest-list">
                {(node.guests || []).map(g => (
                  <GuestCard key={`${g.type}-${g.vmid}`} guest={g} unlocked={unlocked} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function HostCard({ host, unlocked }) {
  const [expanded, setExpanded] = useState(false)
  const statusColor = host.online ? 'var(--green)' : 'var(--red)'
  const blurClass = unlocked ? '' : 'blurred-text'
  const hasLink = !!host.link
  const isUnknownIp = host.ip === '0.0.0.0'

  return (
    <div className="infra-card" style={{ borderColor: host.online ? 'var(--border)' : 'rgba(255,71,87,0.3)' }}>
      <div className="infra-card-header" onClick={() => setExpanded(!expanded)}>
        <div className="infra-card-title">
          <span className="infra-status-dot" style={{ background: isUnknownIp ? 'var(--text-muted)' : statusColor, boxShadow: isUnknownIp ? 'none' : `0 0 5px ${statusColor}` }} />
          <span className="infra-name mono" style={{ fontWeight: 600 }}>{host.name}</span>
          {hasLink && (
            <a
              href={host.link}
              target="_blank"
              rel="noopener noreferrer"
              title={host.link}
              onClick={e => e.stopPropagation()}
              style={{ fontSize: '0.68rem', color: 'var(--blue)', textDecoration: 'none', border: '1px solid var(--blue)', borderRadius: 3, padding: '1px 5px', lineHeight: 1.4, cursor: 'pointer' }}
            >
              ↗ link
            </a>
          )}
          {isUnknownIp ? (
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 600 }}>ip unknown</span>
          ) : (
            <span style={{ fontSize: '0.7rem', color: host.online ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
              {host.online ? 'online' : 'offline'}
            </span>
          )}
        </div>
        <div className="infra-card-meta">
          <span className={`mono ${blurClass}`} style={{ fontSize: '0.73rem' }}>{unlocked ? (isUnknownIp ? '?.?.?.?' : host.ip) : '---.---.---.---'}</span>
          <span className="text-muted" style={{ fontSize: '0.72rem', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{host.role}</span>
          <span className="infra-expand-icon">{expanded ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>

      {expanded && (
        <div className="infra-card-body">
          <div className="infra-detail-grid">
            <div className="infra-detail-col">
              <div className="infra-section-label">Host Info</div>
              <div className="infra-detail-info">
                <div><span className="text-muted">IP:</span> <span className={`mono ${blurClass}`}>{unlocked ? (isUnknownIp ? 'unknown — update hosts.py' : host.ip) : '---'}</span></div>
                <div><span className="text-muted">Group:</span> {host.group}</div>
                <div><span className="text-muted">Check port:</span> <span className="mono">{host.check_port}</span></div>
                {hasLink && <div><span className="text-muted">Dashboard:</span> <a href={host.link} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)', fontSize: '0.78rem' }}>{host.link}</a></div>}
              </div>
            </div>
            <div className="infra-detail-col">
              <div className="infra-section-label">Services</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                {(host.services || []).map(s => (
                  <span key={s} style={{ fontSize: '0.7rem', padding: '2px 7px', borderRadius: 4, border: '1px solid var(--border)', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>{s}</span>
                ))}
              </div>
            </div>
          </div>
          {unlocked && !isUnknownIp && host.online && <PortResults ip={host.ip} />}
          {unlocked && !isUnknownIp && !host.online && <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: 8 }}>Host offline — port scan skipped</div>}
          {unlocked && isUnknownIp && <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: 8 }}>IP unknown — update hosts.py to enable health checks</div>}
          {!unlocked && <div className="text-muted" style={{ fontSize: '0.78rem', marginTop: 8 }}>Unlock to scan ports</div>}
        </div>
      )}
    </div>
  )
}

function hostGroupColor(onlineCount, total) {
  if (onlineCount === total) return 'var(--green)'
  if (onlineCount === 0) return 'var(--red)'
  return 'var(--amber)'
}

function loadGroupOrder(group, hosts) {
  try {
    const saved = localStorage.getItem(`infra_order_${group}`)
    if (!saved) return hosts
    const names = JSON.parse(saved)
    const byName = Object.fromEntries(hosts.map(h => [h.name, h]))
    const ordered = names.map(n => byName[n]).filter(Boolean)
    const added = hosts.filter(h => !names.includes(h.name))
    return [...ordered, ...added]
  } catch {
    return hosts
  }
}

function HostGroup({ group, hosts, unlocked }) {
  const [collapsed, setCollapsed] = useState(false)
  const [order, setOrder] = useState(() => loadGroupOrder(group, hosts))
  const dragIdx = React.useRef(null)
  const dragOverIdx = React.useRef(null)

  // Sync when live data arrives (new hosts or status changes)
  React.useEffect(() => {
    setOrder(prev => {
      const byName = Object.fromEntries(hosts.map(h => [h.name, h]))
      const merged = prev.map(p => byName[p.name] || p)
      const added = hosts.filter(h => !prev.find(p => p.name === h.name))
      return [...merged, ...added]
    })
  }, [hosts])

  const onDragStart = (i) => { dragIdx.current = i }
  const onDragOver = (e, i) => { e.preventDefault(); dragOverIdx.current = i }
  const onDrop = () => {
    const from = dragIdx.current
    const to = dragOverIdx.current
    if (from === null || to === null || from === to) return
    const next = [...order]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setOrder(next)
    localStorage.setItem(`infra_order_${group}`, JSON.stringify(next.map(h => h.name)))
    dragIdx.current = null
    dragOverIdx.current = null
  }
  const onDragEnd = () => { dragIdx.current = null; dragOverIdx.current = null }

  const onlineCount = order.filter(h => h.online).length

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', cursor: 'pointer', borderBottom: '1px solid var(--border)', marginBottom: 8 }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', flex: 1 }}>{group}</span>
        <span style={{ fontSize: '0.72rem', color: hostGroupColor(onlineCount, order.length), fontFamily: 'var(--mono)' }}>
          {onlineCount}/{order.length} online
        </span>
        <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', opacity: 0.5 }} title="Drag cards to reorder">⠿</span>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{collapsed ? '\u25BC' : '\u25B2'}</span>
      </div>
      {!collapsed && (
        <div className="infra-guest-list">
          {order.map((h, i) => (
            <div
              key={h.name}
              draggable
              onDragStart={() => onDragStart(i)}
              onDragOver={e => onDragOver(e, i)}
              onDrop={onDrop}
              onDragEnd={onDragEnd}
              style={{ cursor: 'grab' }}
            >
              <HostCard host={h} unlocked={unlocked} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function NetworkInventory() {
  const { data, loading } = useApi('/api/network/inventory', 60000)
  const { data: hostsData, loading: hostsLoading } = useApi('/api/network/hosts', 30000)
  const [scanningAll, setScanningAll] = useState(false)
  const [unlocked, setUnlocked] = useState(() => gateIsValid('security_gate_net'))

  const scanAll = async () => {
    setScanningAll(true)
    const token = sessionStorage.getItem(TOKEN_KEY) || ''
    try { await fetch('/api/network/scan-all', { method: 'POST', headers: { 'X-Gate-Token': token } }) } catch {}
    setScanningAll(false)
  }

  // Group hosts by their group field
  const hostGroups = {}
  if (hostsData) {
    for (const h of hostsData) {
      if (!hostGroups[h.group]) hostGroups[h.group] = []
      hostGroups[h.group].push(h)
    }
  }

  const groupOrder = Object.keys(hostGroups).sort((a, b) => ['Core','Nodes','Tools','Production','Workstations','Monitoring'].indexOf(a) - ['Core','Nodes','Tools','Production','Workstations','Monitoring'].indexOf(b))

  const onlineCount = hostsData ? hostsData.filter(h => h.online).length : 0
  const totalCount = hostsData ? hostsData.length : 0
  const onlineColor = hostsData
    ? (onlineCount === totalCount ? 'var(--green)' : onlineCount === 0 ? 'var(--red)' : 'var(--amber)')
    : 'var(--text-muted)'

  return (
    <div className="network-inventory gate-locked-wrapper">
      {!unlocked && (
        <div className="gate-locked-overlay">
          <GateUnlock storageKey="security_gate_net" label="Enter credentials to reveal host details:" onUnlock={() => setUnlocked(true)} />
        </div>
      )}
      {unlocked && <GateSessionBar gateKey="security_gate_net" onLock={() => setUnlocked(false)} />}

      <div className={unlocked ? '' : 'gate-content-blur'}>
      <div className="net-header" style={{ marginTop: 0, alignItems: 'baseline' }}>
        <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', letterSpacing: '0.01em' }}>
          Infrastructure Hosts:
        </h2>
        {hostsLoading && !hostsData && <span className="text-muted" style={{ fontSize: '0.82rem' }}>Checking...</span>}
        {hostsData && (
          <span style={{ fontSize: '0.92rem', fontFamily: 'var(--mono)', fontWeight: 700, color: onlineColor }}>
            {onlineCount}/{totalCount} online
          </span>
        )}
      </div>

      {hostsData && groupOrder
        .filter(g => hostGroups[g])
        .map(g => <HostGroup key={g} group={g} hosts={hostGroups[g]} unlocked={unlocked} />)
      }

      {/* Hypervisor — Proxmox cluster node detail */}
      <div className="net-header" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--border)', marginBottom: 8, width: '100%' }}>
          <span style={{ fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', flex: 1 }}>Hypervisor</span>
          {unlocked && (
            <button className="scan-btn" onClick={scanAll} disabled={scanningAll}>
              {scanningAll ? 'Scanning All...' : 'Scan All Nodes'}
            </button>
          )}
        </div>
      </div>
      {data && (
        <div className="infra-node-list">
          {data.map((node, i) => (
            <NodeCard key={i} node={node} unlocked={unlocked} />
          ))}
        </div>
      )}
      </div> {/* end gate-content-blur wrapper */}
    </div>
  )
}
