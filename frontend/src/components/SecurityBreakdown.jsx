import React from 'react'
import { useApi } from '../hooks/useApi'

function HBar({ label, value, max, color = 'var(--red)', sublabel }) {
  const pct = max > 0 ? (value / max) * 100 : 0
  return (
    <div className="sbd-bar-row">
      <span className="sbd-bar-label">{label}</span>
      <div className="sbd-bar-track">
        <div className="sbd-bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="sbd-bar-val">{value.toLocaleString()}</span>
      {sublabel && <span className="sbd-bar-sub">{sublabel}</span>}
    </div>
  )
}

function ScenarioLabel({ scenario }) {
  const colors = {
    'http:exploit': 'var(--red)',
    'http:scan': 'var(--amber)',
    'ssh:bf': 'var(--red)',
    'ssh:bruteforce': 'var(--red)',
    'http:bruteforce': 'var(--amber)',
    'http:crawl': '#8b949e',
    'port:scan': 'var(--amber)',
    'http:dos': 'var(--red)',
  }
  const matched = Object.keys(colors).find(k => scenario.toLowerCase().includes(k.split(':')[0]) && scenario.toLowerCase().includes(k.split(':')[1] || ''))
  const color = matched ? colors[matched] : 'var(--text-muted)'
  return <span style={{ color, fontFamily: 'var(--mono)', fontSize: '0.75rem' }}>{scenario}</span>
}

export default function SecurityBreakdown() {
  const { data, loading } = useApi('/api/breakdown', 120000)

  if (loading && !data) return <div className="loading" style={{ height: 120 }}>Loading breakdown…</div>
  if (!data) return null

  const maxCountry = data.countries[0]?.count || 1
  const maxScenario = data.scenarios[0]?.count || 1
  const maxIsp = data.isps[0]?.count || 1

  return (
    <div className="sbd-root">

      {/* Countries */}
      <div className="sbd-panel">
        <div className="sbd-panel-title">Top Attacking Countries</div>
        <div className="sbd-bars">
          {data.countries.map(c => (
            <HBar
              key={c.code}
              label={<>{c.country}</>}
              value={c.count}
              max={maxCountry}
              color="var(--red)"
            />
          ))}
        </div>
      </div>

      {/* Scenarios */}
      <div className="sbd-panel">
        <div className="sbd-panel-title">Attack Scenarios</div>
        <div className="sbd-bars">
          {data.scenarios.map(s => (
            <HBar
              key={s.scenario}
              label={<ScenarioLabel scenario={s.scenario} />}
              value={s.count}
              max={maxScenario}
              color="var(--amber)"
            />
          ))}
        </div>

      </div>

      {/* ISPs */}
      <div className="sbd-panel">
        <div className="sbd-panel-title">Top Attacking ISPs</div>
        <div className="sbd-isp-list">
          {data.isps.map((s, i) => (
            <div key={i} className="sbd-isp-row">
              <span className="sbd-isp-rank text-muted">{i + 1}</span>
              <span className="sbd-isp-name">{s.isp}</span>
              <div className="sbd-isp-bar-wrap">
                <div className="sbd-isp-bar" style={{ width: `${(s.count / maxIsp) * 100}%` }} />
              </div>
              <span className="sbd-isp-count">{s.count.toLocaleString()}</span>
            </div>
          ))}
        </div>
        <div className="sbd-total">Total active bans: <strong>{(data.total || 0).toLocaleString()}</strong> · <span className="text-muted">{(data.ungeolocated || 0).toLocaleString()} without geo data ({(data.geolocated || 0).toLocaleString()} sampled)</span></div>
      </div>

    </div>
  )
}
