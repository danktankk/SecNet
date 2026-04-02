import React, { useState } from 'react'
import { useApi } from '../hooks/useApi'

const SEV_CONFIG = {
  critical: { color: '#ff4757', bg: 'rgba(255,71,87,0.12)', label: 'CRITICAL' },
  high:     { color: '#ff8c42', bg: 'rgba(255,140,66,0.12)', label: 'HIGH' },
  medium:   { color: '#ffb700', bg: 'rgba(255,183,0,0.12)',  label: 'MEDIUM' },
  low:      { color: '#58a6ff', bg: 'rgba(88,166,255,0.12)', label: 'LOW' },
}

function AttackGroup({ group, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const cfg = SEV_CONFIG[group.severity] || SEV_CONFIG.low

  return (
    <div className="ti-group" style={{ borderLeft: `3px solid ${cfg.color}` }}>
      <div className="ti-group-header" onClick={() => setOpen(o => !o)}>
        <div className="ti-group-left">
          <span className="ti-sev-badge" style={{ color: cfg.color, background: cfg.bg }}>
            {cfg.label}
          </span>
          <span className="ti-group-name">{group.type}</span>
          <span className="ti-group-count">{group.count} IP{group.count !== 1 ? 's' : ''}</span>
        </div>
        <div className="ti-group-right">
          <span className="ti-blocked-badge">BLOCKED</span>
          <span className="ti-chevron">{open ? '▲' : '▼'}</span>
        </div>
      </div>
      {open && (
        <div className="ti-ip-list">
          {group.ips.map(ip => (
            <span key={ip} className="ti-ip">{ip}</span>
          ))}
          {group.count > group.ips.length && (
            <span className="ti-ip ti-ip-more">+{group.count - group.ips.length} more</span>
          )}
        </div>
      )}
    </div>
  )
}

export default function ThreatIntel() {
  const { data, loading } = useApi('/api/threat-intel', 30000)

  if (loading || !data) {
    return <div className="loading">Loading threat intelligence…</div>
  }

  const hasLocal = data.local_total > 0
  const hasHigh = data.has_high_severity || data.has_brute_force

  return (
    <div className="ti-container">
      <div className="ti-header">
        <div className="ti-shield-stat">
          <div className="ti-shield-icon">⛨</div>
          <div>
            <div className="ti-shield-num">{(data.community_blocks || 0).toLocaleString()}</div>
            <div className="ti-shield-label">Community Shield — Pre-emptive Blocks</div>
            <div className="ti-shield-sub">CAPI community blocklist + threat feeds — background noise, not your traffic</div>
          </div>
        </div>

        <div className={`ti-local-stat ${hasLocal ? (hasHigh ? 'ti-local-warn' : 'ti-local-active') : 'ti-local-clean'}`}>
          <div className="ti-local-num">{data.local_total}</div>
          <div className="ti-local-label">
            {data.local_total === 0
              ? 'No Perimeter Detections'
              : `Perimeter Detection${data.local_total !== 1 ? 's' : ''}`}
          </div>
          <div className="ti-local-sub">
            {data.local_total === 0
              ? 'No IPs have probed your services in the active ban window'
              : 'IPs that hit your services — all banned by local agent'}
          </div>
        </div>
      </div>

      {hasLocal && (
        <div className="ti-groups">
          <div className="ti-groups-title">Attack Type Breakdown — All Blocked</div>
          {(data.groups || []).map(g => (
            <AttackGroup
              key={g.type}
              group={g}
              defaultOpen={g.severity === 'critical' || g.severity === 'high'}
            />
          ))}
        </div>
      )}
    </div>
  )
}
