import React from 'react'

export function StatusDot({ ok, warn, size = 7 }) {
  const color = ok ? 'var(--green)' : warn ? 'var(--amber)' : 'var(--red)'
  return (
    <span style={{
      display: 'inline-block', width: size, height: size, borderRadius: '50%',
      background: color, boxShadow: `0 0 5px ${color}`, flexShrink: 0
    }} />
  )
}

export function UtilBar({ value, warn = 60, danger = 85, height = 4 }) {
  const pct = Math.min(100, value || 0)
  const color = pct >= danger ? 'var(--red)' : pct >= warn ? 'var(--amber)' : 'var(--green)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <div style={{ flex: 1, height, background: 'rgba(255,255,255,0.06)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: '0.68rem', color, fontFamily: 'var(--mono)', width: 26, textAlign: 'right' }}>{pct}%</span>
    </div>
  )
}

export function FirmwareBadge({ version, upgradable, upgradeTo }) {
  if (!version) return null
  if (upgradable) {
    return (
      <span className="net-fw-badge net-fw-outdated" title={upgradeTo ? `Update to ${upgradeTo}` : 'Update available'}>
        {version} ↑
      </span>
    )
  }
  return <span className="net-fw-badge net-fw-current">{version}</span>
}
