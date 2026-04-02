import React, { useState, useEffect, useRef } from 'react'
import { useApi, useWebSocket } from './hooks/useApi'
import StatCards from './components/StatCards'
import ThreatIntel from './components/ThreatIntel'
import GeoMap from './components/GeoMap'
import Timeline from './components/Timeline'
import AiChat from './components/AiChat'
import { BansFeed, AttackOrigins, UnifiEventsFeed, AttackBreakdown } from './components/LogsTab'
import NetworkInventory from './components/NetworkInventory'
import NetworkHealth from './components/NetworkHealth'
import Workstations from './components/Workstations'
import SecurityBreakdown from './components/SecurityBreakdown'

// feature: null = always shown
// feature: string = show if that feature is enabled
// feature: [string, ...] = show if ANY of those features are enabled
const ALL_TABS = [
  { id: 'security',       label: 'Security',       icon: '\u2B21', feature: null },
  { id: 'infrastructure', label: 'Infrastructure',  icon: '\u2B22', feature: 'proxmox' },
  { id: 'network',        label: 'Network',         icon: '\u25C8', feature: 'unifi' },
  { id: 'workstations',   label: 'Workstations',    icon: '\u25FB', feature: 'workstations' },
  { id: 'logs',           label: 'Logs',            icon: '\u25A4', feature: ['crowdsec', 'loki', 'unifi'] },
]

const LEVEL_CONFIG = {
  nominal:    { cls: 'threat-nominal',    label: 'Nominal' },
  monitoring: { cls: 'threat-monitoring', label: 'Monitoring' },
  elevated:   { cls: 'threat-elevated',   label: 'Elevated' },
  critical:   { cls: 'threat-critical',   label: 'Critical' },
  low:        { cls: 'threat-nominal',    label: 'Nominal' },
}

const ExpandIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <polyline points="1,5 1,1 5,1"/>
    <polyline points="8,1 12,1 12,5"/>
    <polyline points="12,8 12,12 8,12"/>
    <polyline points="5,12 1,12 1,8"/>
  </svg>
)

const CompressIcon = () => (
  <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <polyline points="5,1 5,5 1,5"/>
    <polyline points="8,5 12,5 12,1"/>
    <polyline points="12,8 12,12 8,12"/>
    <polyline points="1,8 1,12 5,12"/>
  </svg>
)

function ThreatBadge({ s }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  if (!s) return null

  const cfg = LEVEL_CONFIG[s.threat_level] || LEVEL_CONFIG.nominal
  const reasons = s.threat_reasons || []
  const isActionable = s.threat_level === 'elevated' || s.threat_level === 'critical'

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <span
        className={`threat-badge ${cfg.cls}`}
        onClick={() => isActionable && setOpen(o => !o)}
        style={{ cursor: isActionable ? 'pointer' : 'default' }}
        title={isActionable ? 'Click for details' : undefined}
      >
        {cfg.label}
        {isActionable && <span style={{ marginLeft: 5, fontSize: '0.65rem', opacity: 0.7 }}>{'\u25BC'}</span>}
      </span>

      {open && isActionable && (
        <div className="threat-detail-popup">
          <div className="threat-detail-title">Why {cfg.label}?</div>
          {reasons.length > 0
            ? reasons.map((r, i) => <div key={i} className="threat-detail-item">{r}</div>)
            : <div className="threat-detail-item">No specific reason recorded.</div>
          }
        </div>
      )}
    </div>
  )
}

export default function App() {
  const { data: summary, refreshing: r1 } = useApi('/api/summary', 15000)
  const { data: decisions, refreshing: r2 } = useApi('/api/decisions', 30000)
  const { data: timeline, refreshing: r3 } = useApi('/api/timeline?range=24h', 60000)
  const { data: unifiLogs, refreshing: r4 } = useApi('/api/logs/unifi?limit=50', 20000)
  const { data: traefikLogs, refreshing: r5 } = useApi('/api/logs/traefik?limit=50', 20000)
  const { data: crowdsecAlerts, refreshing: r6 } = useApi('/api/logs/crowdsec?limit=50', 20000)
  const { data: featuresData } = useApi('/api/features', 0)
  const anyRefreshing = r1 || r2 || r3 || r4 || r5 || r6
  const wsMsg = useWebSocket('/ws/feed')

  const [live, setLive] = useState(null)
  const [tab, setTab] = useState('security')
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [lightMode, setLightMode] = useState(() => {
    const stored = localStorage.getItem('theme') === 'light'
    if (stored) document.body.classList.add('light-mode')
    return stored
  })

  const toggleTheme = () => {
    const next = !lightMode
    setLightMode(next)
    document.body.classList.toggle('light-mode', next)
    localStorage.setItem('theme', next ? 'light' : 'dark')
  }

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {})
    } else {
      document.exitFullscreen().catch(() => {})
    }
  }

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  useEffect(() => {
    if (wsMsg?.type === 'summary') setLive(wsMsg.data)
  }, [wsMsg])

  // Check if a single feature key is enabled
  const featureEnabled = (key) => {
    if (!featuresData || !key) return true
    const v = featuresData[key]
    if (v === undefined) return true
    if (typeof v === 'boolean') return v
    return v.enabled
  }

  // Tab visibility: null = always, string = single feature, array = any-of
  const tabVisible = (feature) => {
    if (feature === null) return true
    if (Array.isArray(feature)) return feature.some(f => featureEnabled(f))
    return featureEnabled(feature)
  }

  const visibleTabs = ALL_TABS.filter(t => tabVisible(t.feature))

  // If current tab got hidden by feature flags, fall back to first visible
  useEffect(() => {
    const ids = visibleTabs.map(t => t.id)
    if (!ids.includes(tab)) setTab(ids[0] || 'security')
  }, [featuresData])

  const s = live || summary
  const now = s ? new Date(s.timestamp * 1000).toLocaleTimeString() : '--'

  // Which data sources are live — used to conditionally render sections
  const hasCrowdsec = featureEnabled('crowdsec')
  const hasLoki = featureEnabled('loki')
  const hasPrometheus = featureEnabled('prometheus')
  const hasUnifi = featureEnabled('unifi')

  return (
    <div className="dashboard">
      {anyRefreshing && <div className="updating-bar" />}
      <div className="header">
        <h1>Security Posture &amp; Network Operations {'\u00B7'} Real-Time Monitoring</h1>
        <div className="meta">
          <span>Last update: {now}{anyRefreshing && <span className="updating-dot" />}</span>
          <ThreatBadge s={s} />
          <button onClick={toggleTheme} className="header-btn">
            {lightMode ? 'Dark' : 'Light'}
          </button>
          <button
            onClick={toggleFullscreen}
            className="header-btn header-btn-fs"
            title={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
          >
            {isFullscreen ? <CompressIcon /> : <ExpandIcon />}
          </button>
        </div>
      </div>

      {featureEnabled('openai') && <AiChat />}

      <div className="tab-bar">
        <span className="tab-bar-label">{'\u25C9'} VIEW</span>
        <div className="tab-bar-divider" />
        {visibleTabs.map(t => (
          <button
            key={t.id}
            className={`tab-btn ${tab === t.id ? 'tab-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <span className="tab-icon">{t.icon}</span>
            <span className="tab-label">{t.label}</span>
          </button>
        ))}
      </div>

      {tab === 'security' && (
        <>
          {(hasCrowdsec || hasPrometheus) && <StatCards summary={s} />}
          {hasCrowdsec && <ThreatIntel />}
          <div className="split-row">
            {hasCrowdsec && (
              <div className="panel">
                <h3>Attacker Map</h3>
                <GeoMap decisions={decisions} />
              </div>
            )}
            {hasPrometheus && (
              <div className="panel">
                <h3>Ban Trend + Event Rate (24h)</h3>
                <Timeline data={timeline} />
              </div>
            )}
          </div>
          {hasCrowdsec && <SecurityBreakdown />}
          {!hasCrowdsec && !hasPrometheus && (
            <div className="panel" style={{ textAlign: 'center', padding: '3rem 1rem', opacity: 0.5 }}>
              No security data sources configured. Enable CrowdSec or Prometheus in your environment.
            </div>
          )}
        </>
      )}

      {tab === 'infrastructure' && <NetworkInventory />}

      {tab === 'network' && <NetworkHealth />}

      {tab === 'workstations' && <Workstations />}

      {tab === 'logs' && (
        <div className="feed-row feed-row-4">
          {hasCrowdsec && <BansFeed decisions={decisions} />}
          {hasCrowdsec && <AttackOrigins decisions={decisions} />}
          {(hasLoki || hasUnifi) && <UnifiEventsFeed data={unifiLogs} />}
          {hasCrowdsec && <AttackBreakdown decisions={decisions} />}
          {!hasCrowdsec && !hasLoki && !hasUnifi && (
            <div className="panel" style={{ textAlign: 'center', padding: '3rem 1rem', opacity: 0.5 }}>
              No log sources configured.
            </div>
          )}
        </div>
      )}
    </div>
  )
}
