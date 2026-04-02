import React, { useMemo, useState } from 'react'

// ── Active Bans Feed ─────────────────────────────────────────────────────────

const REASON_COLOR = {
  'http:exploit':        'var(--red)',
  'http:scan':           'var(--amber)',
  'ssh:':                'var(--amber)',
  'crowdsecurity/http':  'var(--amber)',
  'crowdsecurity/ssh':   'var(--amber)',
}

function reasonColor(reason) {
  for (const [k, v] of Object.entries(REASON_COLOR)) {
    if (reason?.startsWith(k)) return v
  }
  return 'var(--text-muted)'
}

function originBadge(origin) {
  if (origin === 'CAPI') return { label: 'CAPI', color: 'var(--blue)' }
  if (origin === 'lists') return { label: 'LIST', color: 'var(--text-muted)' }
  return { label: 'LOCAL', color: 'var(--red)' }
}

export function BansFeed({ decisions }) {
  const [filter, setFilter] = useState('all')

  const items = useMemo(() => {
    if (!decisions) return []
    let d = decisions
    if (filter === 'local') d = d.filter(x => x.origin !== 'CAPI' && x.origin !== 'lists')
    else if (filter === 'capi') d = d.filter(x => x.origin === 'CAPI')
    return d.slice(0, 80)
  }, [decisions, filter])

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span className="log-panel-title">Active Bans</span>
        <span className="log-panel-count">{decisions?.length?.toLocaleString() || 0}</span>
        <div className="log-filter-row">
          {['all', 'local', 'capi'].map(f => (
            <button
              key={f}
              className={`log-filter-btn${filter === f ? ' active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      <div className="log-scroll">
        {items.map((d, i) => {
          const badge = originBadge(d.origin)
          return (
            <div key={i} className="log-ban-row">
              <span className="log-ban-ip mono">{d.ip}</span>
              <span className="log-ban-reason" style={{ color: reasonColor(d.reason) }} title={d.reason}>
                {d.reason?.replace('crowdsecurity/', '')}
              </span>
              <span className="log-ban-country" title={d.country}>{d.country_code || '??'}</span>
              <span className="log-ban-origin" style={{ color: badge.color }}>{badge.label}</span>
            </div>
          )
        })}
        {!decisions && <div className="log-empty">Loading…</div>}
        {decisions && items.length === 0 && <div className="log-empty">No bans match filter</div>}
      </div>
    </div>
  )
}

// ── Attack Origins Analytics ─────────────────────────────────────────────────

function BarRow({ label, count, max, color }) {
  const pct = max > 0 ? (count / max) * 100 : 0
  return (
    <div className="log-bar-row">
      <span className="log-bar-label" title={label}>{label}</span>
      <div className="log-bar-track">
        <div style={{ width: `${pct}%`, height: '100%', background: color, opacity: 0.6, borderRadius: 2, transition: 'width 0.4s' }} />
      </div>
      <span className="log-bar-val mono">{count.toLocaleString()}</span>
    </div>
  )
}

export function AttackOrigins({ decisions }) {
  const { countries, origins, topIsps } = useMemo(() => {
    if (!decisions) return { countries: [], origins: [], topIsps: [] }

    const countryCounts = {}
    const originCounts = {}
    const ispCounts = {}

    for (const d of decisions) {
      if (d.country) countryCounts[d.country] = (countryCounts[d.country] || 0) + 1
      if (d.origin) originCounts[d.origin] = (originCounts[d.origin] || 0) + 1
      if (d.isp) ispCounts[d.isp] = (ispCounts[d.isp] || 0) + 1
    }

    const sort = obj => Object.entries(obj).sort((a, b) => b[1] - a[1])
    return {
      countries: sort(countryCounts).slice(0, 10),
      origins: sort(originCounts),
      topIsps: sort(ispCounts).slice(0, 8),
    }
  }, [decisions])

  const maxCountry = countries[0]?.[1] || 1
  const maxIsp = topIsps[0]?.[1] || 1

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span className="log-panel-title">Attack Origins</span>
      </div>
      <div className="log-scroll">
        <div className="log-section-label">By Country</div>
        {countries.map(([c, n]) => (
          <BarRow key={c} label={c} count={n} max={maxCountry} color="var(--red)" />
        ))}

        <div className="log-section-label" style={{ marginTop: 12 }}>By Source</div>
        {origins.map(([o, n]) => {
          const badge = originBadge(o)
          return <BarRow key={o} label={o} count={n} max={decisions?.length || 1} color={badge.color} />
        })}

        <div className="log-section-label" style={{ marginTop: 12 }}>Top ISPs</div>
        {topIsps.map(([isp, n]) => (
          <BarRow key={isp} label={isp} count={n} max={maxIsp} color="var(--amber)" />
        ))}
      </div>
    </div>
  )
}

// ── UniFi Events ─────────────────────────────────────────────────────────────

function fmtLokiTime(ts) {
  if (!ts) return ''
  try {
    const ms = parseInt(ts) / 1_000_000
    return new Date(ms).toLocaleTimeString()
  } catch { return '' }
}

function cleanUnifiMsg(msg) {
  if (!msg) return ''
  return msg
    .replace(/^\[[\w.-]+\]\.\w+\(\): /, '')  // strip [FP-ML].func():
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function UnifiEventsFeed({ data }) {
  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span className="log-panel-title">UniFi Events</span>
        <span className="log-panel-count">{data?.length || 0}</span>
      </div>
      <div className="log-scroll">
        {!data && <div className="log-empty">Loading…</div>}
        {data && data.length === 0 && <div className="log-empty">No events</div>}
        {(data || []).map((e, i) => (
          <div key={i} className="log-event-row">
            <span className="log-event-time mono">{fmtLokiTime(e.timestamp)}</span>
            <span className="log-event-msg" title={e.message}>{cleanUnifiMsg(e.message)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Attack Breakdown ─────────────────────────────────────────────────────────

export function AttackBreakdown({ decisions }) {
  const { reasons, severities } = useMemo(() => {
    if (!decisions) return { reasons: [], severities: [] }

    const rCounts = {}
    const sCounts = {}

    for (const d of decisions) {
      const r = d.reason?.replace('crowdsecurity/', '') || 'unknown'
      rCounts[r] = (rCounts[r] || 0) + 1
      const s = d.severity || 'mitigated'
      sCounts[s] = (sCounts[s] || 0) + 1
    }

    const sort = obj => Object.entries(obj).sort((a, b) => b[1] - a[1])
    return {
      reasons: sort(rCounts).slice(0, 12),
      severities: sort(sCounts),
    }
  }, [decisions])

  const maxReason = reasons[0]?.[1] || 1

  const sevColor = s => s === 'mitigated' ? 'var(--green)' : s === 'safe' ? 'var(--blue)' : 'var(--amber)'

  return (
    <div className="log-panel">
      <div className="log-panel-header">
        <span className="log-panel-title">Attack Breakdown</span>
      </div>
      <div className="log-scroll">
        <div className="log-section-label">By Scenario</div>
        {reasons.map(([r, n]) => (
          <BarRow key={r} label={r} count={n} max={maxReason} color="var(--amber)" />
        ))}

        <div className="log-section-label" style={{ marginTop: 12 }}>By Severity</div>
        {severities.map(([s, n]) => (
          <BarRow key={s} label={s} count={n} max={decisions?.length || 1} color={sevColor(s)} />
        ))}
      </div>
    </div>
  )
}
