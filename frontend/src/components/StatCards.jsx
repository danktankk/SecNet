import React from 'react'

const cards = [
  { key: 'active_bans', label: 'Active Bans', color: '#00ff87' },
  { key: 'cf_blocks', label: 'CF Blocks', color: '#58a6ff' },
  { key: 'unique_ips', label: 'Unique Attackers', color: '#ffb700' },
  { key: 'ssh_failures', label: 'SSH Failures (24h)', color: '#ff4757' },
  { key: 'alerts', label: 'Total Alerts', color: '#ff4757' },
  { key: 'lapi_requests', label: 'LAPI Requests', color: '#58a6ff' },
  { key: 'bucket_events', label: 'Bucket Events', color: '#ffb700' },
  { key: 'parser_hits', label: 'Log Lines Parsed', color: '#00ff87' },
]

export default function StatCards({ summary }) {
  return (
    <div className="stat-row">
      {cards.map(c => (
        <div className="stat-card" key={c.key}>
          <div className="value" style={{ color: c.color }}>
            {summary ? (summary[c.key] ?? '--').toLocaleString() : '--'}
          </div>
          <div className="label">{c.label}</div>
        </div>
      ))}
    </div>
  )
}
