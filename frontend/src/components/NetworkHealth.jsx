import React, { useState, useMemo } from 'react'
import { useApi } from '../hooks/useApi'
import { fmtBytesRate, fmtBytes, fmtUptime } from '../utils/format'
import GateUnlock from './GateUnlock'
import GateSessionBar from './GateSessionBar'
import { StatusDot, UtilBar, FirmwareBadge } from './ui'
import { gateIsValid, NET_GATE_KEY } from '../utils/gate'


function radioBandLabel(band) {
  if (band === 'ng') return '2.4G'
  if (band === 'na') return '5G'
  if (band === 'nad') return '5G-HD'
  return '6G'
}

// ────────────────────────────────────────────────────────────────────────────
// Status Rail — subsystem health pills across the top
// ────────────────────────────────────────────────────────────────────────────

function StatusRail({ subsystems }) {
  const labels = { wan: 'WAN', www: 'Internet', lan: 'LAN', wlan: 'WiFi', vpn: 'VPN' }
  const order = ['wan', 'www', 'lan', 'wlan', 'vpn']
  const entries = [
    ...order.filter(k => subsystems[k]),
    ...Object.keys(subsystems).filter(k => !order.includes(k)),
  ]

  return (
    <div className="net-status-rail">
      {entries.map(k => {
        const s = subsystems[k]
        const ok = s.status === 'ok'
        const warn = s.status === 'warning'
        const color = ok ? 'var(--green)' : warn ? 'var(--amber)' : 'var(--red)'
        return (
          <div key={k} className="net-sub-pill" style={{ borderColor: `${color}44` }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%', background: color,
              boxShadow: `0 0 6px ${color}`, display: 'inline-block', flexShrink: 0,
              animation: !ok ? 'pulse-border 1.8s ease-in-out infinite' : 'none',
            }} />
            <span className="net-sub-pill-label">{labels[k] || k.toUpperCase()}</span>
            <span className="net-sub-pill-status" style={{ color }}>{s.status}</span>
            {s.xput_down > 0 && (
              <span className="net-sub-pill-speed">
                ↓{s.xput_down.toFixed(0)} ↑{(s.xput_up || 0).toFixed(0)} Mbps
              </span>
            )}
            {s.latency > 0 && (
              <span className="net-sub-pill-speed">{s.latency}ms</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Vitals Bar — five key metrics in a segmented strip
// ────────────────────────────────────────────────────────────────────────────

function VitalsBar({ health, devices, clients }) {
  const totalClients = clients?.total || 0
  const apCount = devices?.aps?.length || 0
  const gw = devices?.gateways?.[0]
  const wanSub = health?.subsystems?.wan
  const wlanSub = health?.subsystems?.wlan

  const metrics = [
    { label: 'Connected', value: String(totalClients), sub: 'clients' },
    { label: 'Access Points', value: String(apCount), sub: 'online' },
    gw?.wan_ip
      ? { label: 'WAN IP', value: gw.wan_ip, mono: true, sub: gw.wan_speed > 0 ? `${gw.wan_speed} Mbps` : null }
      : null,
    wanSub?.xput_down > 0
      ? { label: 'Throughput', value: `↓${wanSub.xput_down.toFixed(0)} / ↑${(wanSub.xput_up || 0).toFixed(0)}`, mono: true, sub: 'Mbps' }
      : null,
    gw?.uptime
      ? { label: 'GW Uptime', value: gw.uptime }
      : null,
    wlanSub
      ? { label: 'WiFi Users', value: String((wlanSub.num_user || 0) + (wlanSub.num_iot || 0) + (wlanSub.num_guest || 0)), sub: 'connected' }
      : null,
  ].filter(Boolean).slice(0, 5)

  return (
    <div className="net-vitals-bar">
      {metrics.map((m, i) => (
        <div key={i} className="net-vital">
          <span className="net-vital-label">{m.label}</span>
          <span className={`net-vital-value${m.mono ? ' mono' : ''}`}>{m.value}</span>
          {m.sub && <span className="net-vital-sub">{m.sub}</span>}
        </div>
      ))}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Infrastructure column — gateway + switches
// ────────────────────────────────────────────────────────────────────────────

function portColor(p) {
  const speed = p.speed || 0
  const hasSpeed = typeof p.speed === 'number'
  if (!p.up) return 'rgba(255,255,255,0.07)'
  if (!hasSpeed) return 'var(--green)'
  if (speed >= 10000) return '#48cae4'
  if (speed >= 1000) return 'var(--green)'
  if (speed >= 100) return 'var(--amber)'
  return 'var(--red)'
}

function portLabel(p) {
  const speed = p.speed || 0
  const hasSpeed = typeof p.speed === 'number'
  if (!p.up) return 'down'
  if (!hasSpeed) return 'up'
  if (speed >= 10000) return '10G'
  if (speed >= 1000) return '1G'
  if (speed >= 100) return '100M'
  return `${speed}M`
}

function portTitle(p, i) {
  const label = portLabel(p)
  const idx = p.idx || i + 1
  const customName = p.name && !p.name.match(/^Port \d+$/) ? ` · ${p.name}` : ''
  return `Port ${idx}: ${label}${p.poe_enable ? ' · PoE' : ''}${p.poe_power > 0 ? ` · ${p.poe_power}W` : ''}${customName}`
}

function PortDot({ p, i }) {
  const color = portColor(p)
  return (
    <div
      className="net-port-dot"
      style={{
        background: color,
        boxShadow: p.up ? `0 0 3px ${color}40` : 'none',
        border: p.poe_enable ? '1px solid var(--amber)' : '1px solid transparent',
      }}
      title={portTitle(p, i)}
    />
  )
}

function PortGrid({ ports, portCount }) {
  if (!ports || ports.length === 0) return null

  // Separate RJ45 (GE) ports from SFP/SFP+ ports
  const gePorts = ports.filter(p => !p.media || p.media === 'GE')
  const sfpPorts = ports.filter(p => p.media && p.media !== 'GE')
  const geCount = gePorts.length

  // For switches with ≥24 GE ports, render as 2-row faceplate (odds top, evens bottom)
  if (geCount >= 24) {
    const topRow = gePorts.filter((_, i) => i % 2 === 0)  // odd-numbered ports (1,3,5...)
    const bottomRow = gePorts.filter((_, i) => i % 2 === 1)  // even-numbered ports (2,4,6...)

    return (
      <div className="net-port-faceplate">
        <div className="net-port-panel">
          <div className="net-port-row">
            {topRow.map((p, i) => <PortDot key={p.idx || i * 2} p={p} i={i * 2} />)}
          </div>
          <div className="net-port-row">
            {bottomRow.map((p, i) => <PortDot key={p.idx || i * 2 + 1} p={p} i={i * 2 + 1} />)}
          </div>
        </div>
        {sfpPorts.length > 0 && (
          <div className="net-port-sfp-group">
            <span className="net-port-sfp-label">SFP</span>
            <div className="net-port-row">
              {sfpPorts.map((p, i) => <PortDot key={p.idx || `sfp-${i}`} p={p} i={geCount + i} />)}
            </div>
          </div>
        )}
      </div>
    )
  }

  // Small switches (5-port flex minis, etc.) — single row
  return (
    <div className="net-port-faceplate">
      <div className="net-port-row">
        {ports.map((p, i) => <PortDot key={p.idx || i} p={p} i={i} />)}
      </div>
    </div>
  )
}

function GatewayCard({ gw }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="net-device-card net-clickable" onClick={() => setOpen(!open)}>
      <div className="net-device-toprow">
        <StatusDot ok={gw.state === 1} />
        <span className="net-device-name">{gw.name}</span>
        <span className="net-device-model">{gw.model}</span>
        <span className="net-expand-icon">{open ? '▲' : '▼'}</span>
      </div>
      {gw.wan_ip && (
        <div className="net-device-meta">
          <span className="mono" style={{ color: 'var(--blue)' }}>{gw.wan_ip}</span>
          {gw.wan_speed > 0 && <span className="text-muted">{gw.wan_speed} Mbps</span>}
          <span className="text-muted">up {gw.uptime}</span>
        </div>
      )}
      <div className="net-util-rows">
        <div className="net-util-row"><span>CPU</span><UtilBar value={gw.cpu_pct} /></div>
        <div className="net-util-row"><span>RAM</span><UtilBar value={gw.mem_pct} /></div>
      </div>
      <div className="net-device-foot">
        <FirmwareBadge version={gw.version} upgradable={gw.upgradable} upgradeTo={gw.upgrade_to_firmware} />
        <span className="net-throughput mono">↓{fmtBytesRate(gw.rx_bytes_r)} ↑{fmtBytesRate(gw.tx_bytes_r)}</span>
      </div>
      {open && (
        <div className="net-device-expanded" onClick={e => e.stopPropagation()}>
          <div className="net-exp-grid">
            <div><span className="text-muted">LAN IP</span><span className="mono">{gw.ip}</span></div>
            <div><span className="text-muted">WAN Name</span><span>{gw.wan_name || '—'}</span></div>
            <div><span className="text-muted">Full Duplex</span><span>{gw.wan_full_duplex ? 'Yes' : 'No'}</span></div>
            <div><span className="text-muted">MAC</span><span className="mono" style={{ fontSize: '0.68rem' }}>{gw.mac}</span></div>
          </div>
        </div>
      )}
    </div>
  )
}

function SwitchCard({ sw }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="net-device-card net-clickable" onClick={() => setOpen(!open)}>
      <div className="net-device-toprow">
        <StatusDot ok={sw.state === 1} />
        <span className="net-device-name">{sw.name}</span>
        <span className="net-device-model">{sw.model}</span>
        <span className="net-expand-icon">{open ? '▲' : '▼'}</span>
      </div>
      <PortGrid ports={sw.ports} />
      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
        <span style={{ color: 'var(--green)' }}>{sw.ports_up}</span>/{sw.port_count} ports up
        {sw.port_count > 0 && sw.ports_up < sw.port_count && (
          <span style={{ color: 'var(--amber)', marginLeft: 8 }}>{sw.port_count - sw.ports_up} down</span>
        )}
      </div>
      {sw.ports && sw.ports.length > 0 && (() => {
        const speeds = new Set(sw.ports.filter(p => p.up && typeof p.speed === 'number').map(p => p.speed))
        if (speeds.size <= 1) return null
        const legend = []
        if (speeds.has(10000)) legend.push({ label: '10G', color: '#48cae4' })
        if (speeds.has(1000)) legend.push({ label: '1G', color: 'var(--green)' })
        if (speeds.has(100)) legend.push({ label: '100M', color: 'var(--amber)' })
        if ([...speeds].some(s => s < 100)) legend.push({ label: '<100M', color: 'var(--red)' })
        if (legend.length === 0) return null
        return (
          <div style={{ display: 'flex', gap: 8, fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 2 }}>
            {legend.map(l => (
              <span key={l.label} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <span style={{ width: 6, height: 6, borderRadius: '50%', background: l.color, display: 'inline-block' }} />
                {l.label}
              </span>
            ))}
          </div>
        )
      })()}
      <div className="net-util-rows">
        <div className="net-util-row"><span>CPU</span><UtilBar value={sw.cpu_pct} /></div>
        <div className="net-util-row"><span>RAM</span><UtilBar value={sw.mem_pct} /></div>
      </div>
      <div className="net-device-foot">
        <FirmwareBadge version={sw.version} upgradable={sw.upgradable} upgradeTo={sw.upgrade_to_firmware} />
        <span className="net-throughput mono">↓{fmtBytesRate(sw.rx_bytes_r)} ↑{fmtBytesRate(sw.tx_bytes_r)}</span>
      </div>
      {open && (
        <div className="net-device-expanded" onClick={e => e.stopPropagation()}>
          <div className="net-exp-grid">
            <div><span className="text-muted">IP</span><span className="mono">{sw.ip}</span></div>
            <div><span className="text-muted">MAC</span><span className="mono" style={{ fontSize: '0.68rem' }}>{sw.mac}</span></div>
            <div><span className="text-muted">Uptime</span><span>{sw.uptime}</span></div>
            <div><span className="text-muted">Clients</span><span>{sw.num_sta}</span></div>
            {sw.poe_budget > 0 && <div><span className="text-muted">PoE Budget</span><span>{sw.poe_budget}W</span></div>}
          </div>
          {sw.ports && sw.ports.length > 0 && (
            <>
              <div className="net-exp-label" style={{ marginTop: 8 }}>Port Table</div>
              <div className="net-port-table">
                <div className="net-port-table-head">
                  <span>#</span><span>Name</span><span>Speed</span><span>PoE</span>
                </div>
                {sw.ports.filter(p => p.up).map((p, i) => (
                  <div key={p.idx || i} className="net-port-table-row">
                    <span className="mono" style={{ color: 'var(--text-muted)' }}>{p.idx || '?'}</span>
                    <span style={{ color: p.name && !p.name.match(/^Port \d+$/) ? 'var(--text)' : 'var(--text-muted)' }}>
                      {p.name || `Port ${p.idx}`}
                    </span>
                    <span className="mono" style={{ color: portColor(p) }}>{portLabel(p)}</span>
                    <span className="mono" style={{ color: p.poe_power > 0 ? 'var(--amber)' : 'var(--text-muted)' }}>
                      {p.poe_power > 0 ? `${p.poe_power}W` : p.poe_enable ? 'on' : '—'}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function InfraColumn({ devices }) {
  return (
    <div className="net-column">
      <div className="net-col-header">Infrastructure</div>
      {(devices?.gateways || []).map((gw, i) => <GatewayCard key={i} gw={gw} />)}
      {(devices?.switches || []).map((sw, i) => <SwitchCard key={i} sw={sw} />)}
      {!devices?.gateways?.length && !devices?.switches?.length && (
        <div className="text-muted" style={{ fontSize: '0.78rem' }}>No infrastructure data</div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Wireless column — access points with radio detail
// ────────────────────────────────────────────────────────────────────────────

function ApCard({ ap, clients }) {
  const [open, setOpen] = useState(false)
  const sat = ap.satisfaction >= 0 ? ap.satisfaction : null
  const satColor = sat === null ? 'var(--text-muted)'
    : sat >= 80 ? 'var(--green)'
    : sat >= 50 ? 'var(--amber)'
    : 'var(--red)'

  const apClients = useMemo(() => {
    if (!clients?.by_vlan) return []
    return Object.values(clients.by_vlan).flat().filter(d => d.ap_name === ap.name)
  }, [clients, ap.name])

  return (
    <div className="net-ap-card net-clickable" onClick={() => setOpen(!open)}>
      <div className="net-ap-toprow">
        <StatusDot ok={ap.state === 1} />
        <span className="net-ap-name">{ap.name}</span>
        <span className="net-ap-clients">{ap.num_sta} cli</span>
        {sat !== null && <span className="net-ap-sat" style={{ color: satColor }}>{sat}%</span>}
        <span className="net-expand-icon">{open ? '▲' : '▼'}</span>
      </div>
      <div className="net-ap-meta">
        <span className="mono text-muted" style={{ fontSize: '0.67rem' }}>{ap.ip}</span>
        <span className="text-muted" style={{ fontSize: '0.67rem' }}>up {ap.uptime}</span>
        <FirmwareBadge version={ap.version} upgradable={ap.upgradable} upgradeTo={ap.upgrade_to_firmware} />
      </div>
      <div className="net-radios">
        {(ap.radios || []).map((r, i) => {
          const cu = r.cu_total || 0
          const cuColor = cu >= 80 ? 'var(--red)' : cu >= 60 ? 'var(--amber)' : 'var(--green)'
          return (
            <div key={i} className="net-radio-row">
              <span className="net-radio-band">{radioBandLabel(r.band)}</span>
              <span className="net-radio-ch">ch{r.channel}</span>
              <span className="net-radio-clients">{r.num_sta}</span>
              <div className="net-radio-cu-track">
                <div style={{ width: `${cu}%`, height: '100%', background: cuColor, borderRadius: 2, transition: 'width 0.5s' }} />
              </div>
              <span className="net-radio-cu-pct" style={{ color: cuColor }}>{cu}%</span>
              {r.tx_power > 0 && <span className="net-radio-pwr">{r.tx_power}dBm</span>}
            </div>
          )
        })}
      </div>
      {open && (
        <div className="net-device-expanded" onClick={e => e.stopPropagation()}>
          {apClients.length > 0 ? (
            <>
              <div className="net-exp-label">Connected Clients ({apClients.length})</div>
              <div className="net-client-mini-list">
                {apClients.map((c, i) => (
                  <div key={i} className="net-client-mini-row">
                    <span className="net-client-mini-name">{c.name}</span>
                    <span className="mono text-muted" style={{ fontSize: '0.67rem' }}>{c.ip}</span>
                    <span className="text-muted" style={{ fontSize: '0.67rem' }}>{c.vlan_name}</span>
                    {c.essid && <span className="text-muted" style={{ fontSize: '0.67rem' }}>{c.essid}</span>}
                    {c.signal < 0 && (
                      <span style={{ fontSize: '0.66rem', color: c.signal < -75 ? 'var(--amber)' : 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
                        {c.signal}dBm
                      </span>
                    )}
                    <span className="mono text-muted" style={{ fontSize: '0.66rem', marginLeft: 'auto' }}>
                      {fmtBytes(c.rx_bytes + c.tx_bytes)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="text-muted" style={{ fontSize: '0.75rem' }}>No clients on this AP</div>
          )}
        </div>
      )}
    </div>
  )
}

function WirelessColumn({ aps, clients }) {
  return (
    <div className="net-column">
      <div className="net-col-header">Wireless ({aps?.length || 0} APs)</div>
      {(aps || []).map((ap, i) => <ApCard key={i} ap={ap} clients={clients} />)}
      {(!aps || aps.length === 0) && (
        <div className="text-muted" style={{ fontSize: '0.78rem' }}>No access points found</div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Intelligence column — offenders + VLAN distribution
// ────────────────────────────────────────────────────────────────────────────

function OffenderSection({ title, accent, children, allClear }) {
  return (
    <div className="net-offender-section" style={{ borderLeftColor: accent }}>
      <div className="net-offender-title" style={{ color: accent }}>{title}</div>
      {allClear
        ? <div className="net-offender-clear">All clear</div>
        : children}
    </div>
  )
}

function BandwidthOffenders({ clients }) {
  const top = useMemo(() => {
    if (!clients?.by_vlan) return []
    return Object.values(clients.by_vlan).flat()
      .sort((a, b) => (b.rx_bytes + b.tx_bytes) - (a.rx_bytes + a.tx_bytes))
      .slice(0, 6)
  }, [clients])

  if (top.length === 0) return null
  const maxBytes = top[0] ? (top[0].rx_bytes + top[0].tx_bytes) : 1

  return (
    <OffenderSection title="Bandwidth Hogs" accent="var(--blue)">
      {top.map((c, i) => {
        const total = c.rx_bytes + c.tx_bytes
        const pct = maxBytes > 0 ? (total / maxBytes) * 100 : 0
        return (
          <div key={i} className="net-offender-row">
            <span className="net-offender-name" title={c.name}>{c.name}</span>
            <span className="net-offender-tag">{c.vlan_name}</span>
            <div className="net-offender-track">
              <div style={{ width: `${pct}%`, height: '100%', background: 'var(--blue)', opacity: 0.55, borderRadius: 2 }} />
            </div>
            <span className="net-offender-val mono">{fmtBytes(total)}</span>
          </div>
        )
      })}
    </OffenderSection>
  )
}

function SignalOffenders({ clients }) {
  const weak = useMemo(() => {
    if (!clients?.by_vlan) return []
    return Object.values(clients.by_vlan).flat()
      .filter(c => c.connection === 'wifi' && c.signal < -68 && c.signal !== 0)
      .sort((a, b) => a.signal - b.signal)
      .slice(0, 6)
  }, [clients])

  return (
    <OffenderSection title="Weak WiFi Signal" accent="var(--amber)" allClear={weak.length === 0}>
      {weak.map((c, i) => {
        const strength = Math.max(0, 100 + c.signal)
        const color = c.signal < -80 ? 'var(--red)' : 'var(--amber)'
        return (
          <div key={i} className="net-offender-row">
            <span className="net-offender-name" title={c.name}>{c.name}</span>
            <span className="net-offender-tag">{c.vlan_name}</span>
            <div className="net-offender-track">
              <div style={{ width: `${strength}%`, height: '100%', background: color, opacity: 0.55, borderRadius: 2 }} />
            </div>
            <span className="net-offender-val mono" style={{ color }}>{c.signal} dBm</span>
          </div>
        )
      })}
    </OffenderSection>
  )
}

function FirmwareAlerts({ devices }) {
  const outdated = useMemo(() => {
    if (!devices) return []
    return [
      ...(devices.gateways || []),
      ...(devices.switches || []),
      ...(devices.aps || []),
    ].filter(d => d.upgradable)
  }, [devices])

  return (
    <OffenderSection title="Firmware Updates Available" accent="var(--red)" allClear={outdated.length === 0}>
      {outdated.map((d, i) => (
        <div key={i} className="net-fw-alert-row">
          <span className="net-offender-name" title={d.name}>{d.name}</span>
          <span className="mono text-muted" style={{ fontSize: '0.68rem' }}>{d.version}</span>
          {d.upgrade_to_firmware && (
            <span style={{ fontSize: '0.66rem', color: 'var(--amber)', fontFamily: 'var(--mono)' }}>
              → {d.upgrade_to_firmware}
            </span>
          )}
        </div>
      ))}
    </OffenderSection>
  )
}

function ApCongestion({ aps }) {
  const congested = useMemo(() =>
    (aps || [])
      .flatMap(ap => (ap.radios || [])
        .filter(r => (r.cu_total || 0) >= 65)
        .map(r => ({ ap: ap.name, band: radioBandLabel(r.band), cu: r.cu_total }))
      )
      .sort((a, b) => b.cu - a.cu),
    [aps]
  )

  if (congested.length === 0) return null

  return (
    <OffenderSection title="AP Channel Congestion" accent="var(--amber)">
      {congested.map((c, i) => (
        <div key={i} className="net-offender-row">
          <span className="net-offender-name">{c.ap}</span>
          <span className="net-radio-band" style={{ width: 'auto', flexShrink: 0 }}>{c.band}</span>
          <div className="net-offender-track">
            <div style={{ width: `${c.cu}%`, height: '100%', background: c.cu >= 80 ? 'var(--red)' : 'var(--amber)', opacity: 0.55, borderRadius: 2 }} />
          </div>
          <span className="net-offender-val mono" style={{ color: c.cu >= 80 ? 'var(--red)' : 'var(--amber)' }}>
            {c.cu}%
          </span>
        </div>
      ))}
    </OffenderSection>
  )
}

function HighUptimeClients({ clients }) {
  const stale = useMemo(() => {
    if (!clients?.by_vlan) return []
    const DAY = 86400
    return Object.values(clients.by_vlan).flat()
      .filter(c => c.uptime > 7 * DAY)
      .sort((a, b) => b.uptime - a.uptime)
      .slice(0, 5)
  }, [clients])

  if (stale.length === 0) return null

  return (
    <OffenderSection title="Long-Connected Devices" accent="#c77dff">
      {stale.map((c, i) => (
        <div key={i} className="net-offender-row">
          <span className="net-offender-name" title={c.name}>{c.name}</span>
          <span className="net-offender-tag">{c.vlan_name}</span>
          <div className="net-offender-track">
            <div style={{ width: `${Math.min(100, c.uptime / 2592000 * 100)}%`, height: '100%', background: '#c77dff', opacity: 0.5, borderRadius: 2 }} />
          </div>
          <span className="net-offender-val mono" style={{ color: '#c77dff' }}>{fmtUptime(c.uptime)}</span>
        </div>
      ))}
    </OffenderSection>
  )
}

const VLAN_COLORS = [
  'var(--blue)', 'var(--green)', 'var(--amber)', '#c77dff',
  '#ff6b6b', '#48cae4', '#f77f00', '#80ffdb',
]

function VlanDistribution({ clients }) {
  const [expanded, setExpanded] = useState(null)
  if (!clients?.by_vlan) return null

  const entries = Object.entries(clients.by_vlan).sort((a, b) => b[1].length - a[1].length)
  const max = entries[0]?.[1].length || 1

  return (
    <div className="net-vlan-section">
      <div className="net-col-header" style={{ marginBottom: 8 }}>Clients by VLAN</div>
      {entries.map(([vlan, devices], idx) => {
        const color = VLAN_COLORS[idx % VLAN_COLORS.length]
        const isOpen = expanded === vlan
        return (
          <div key={vlan}>
            <div
              className="net-vlan-row net-clickable"
              onClick={() => setExpanded(isOpen ? null : vlan)}
            >
              <span className="net-vlan-name">{vlan}</span>
              <div className="net-vlan-track">
                <div style={{ width: `${(devices.length / max) * 100}%`, height: '100%', background: color, opacity: 0.6, borderRadius: 2, transition: 'width 0.4s' }} />
              </div>
              <span className="net-vlan-count mono" style={{ color }}>{devices.length}</span>
              <span style={{ fontSize: '0.58rem', color: 'var(--text-muted)', flexShrink: 0 }}>{isOpen ? '▲' : '▼'}</span>
            </div>
            {isOpen && (
              <div className="net-vlan-expanded">
                <div className="net-client-table-head">
                  <span>Name</span><span>IP</span><span>Type</span><span>Signal</span><span>Usage</span>
                </div>
                {devices.map((c, i) => (
                  <div key={i} className="net-client-table-row">
                    <span className="net-client-mini-name">{c.name}</span>
                    <span className="mono text-muted">{c.ip}</span>
                    <span className="text-muted">{c.connection}</span>
                    <span className="mono" style={{ fontSize: '0.66rem', color: c.signal < -75 ? 'var(--amber)' : 'var(--text-muted)' }}>
                      {c.signal < 0 ? `${c.signal}` : '—'}
                    </span>
                    <span className="mono text-muted">{fmtBytes(c.rx_bytes + c.tx_bytes)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function IntelligenceColumn({ clients, devices }) {
  return (
    <div className="net-column net-intel-col">
      <div className="net-col-header">Intelligence</div>
      <BandwidthOffenders clients={clients} />
      <SignalOffenders clients={clients} />
      <FirmwareAlerts devices={devices} />
      <ApCongestion aps={devices?.aps} />
      <HighUptimeClients clients={clients} />
      <VlanDistribution clients={clients} />
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Alarms panel — collapsible, only shown when alarms exist
// ────────────────────────────────────────────────────────────────────────────

function AlarmsPanel({ alarms }) {
  const [open, setOpen] = useState(false)
  const [detailIdx, setDetailIdx] = useState(null)
  if (!alarms || alarms.length === 0) return null

  return (
    <div className="net-alarms-panel">
      <div className="net-alarms-header net-clickable" onClick={() => setOpen(!open)}>
        <span className="net-alarms-badge">{alarms.length}</span>
        <span style={{ fontSize: '0.78rem', fontWeight: 700 }}>Active Alarms</span>
        <span className="text-muted" style={{ fontSize: '0.68rem', marginLeft: 'auto' }}>
          {open ? '▲ collapse' : '▼ expand'}
        </span>
      </div>
      {open && (
        <div className="net-alarms-list">
          {alarms.map((a, i) => (
            <div key={i}>
              <div
                className="net-alarm-row net-clickable"
                onClick={() => setDetailIdx(detailIdx === i ? null : i)}
              >
                <span className="net-alarm-sub">{a.subsystem || 'system'}</span>
                <span className="net-alarm-msg">{a.msg}</span>
                <span className="net-alarm-time">
                  {a.datetime ? new Date(a.datetime).toLocaleTimeString() : ''}
                </span>
              </div>
              {detailIdx === i && (
                <div className="net-alarm-detail">
                  <span className="text-muted">Key:</span> {a.key || '—'}
                  <span className="text-muted" style={{ marginLeft: 16 }}>Time:</span>{' '}
                  {a.datetime ? new Date(a.datetime).toLocaleString() : '—'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ────────────────────────────────────────────────────────────────────────────
// Root component
// ────────────────────────────────────────────────────────────────────────────

export default function NetworkHealth() {
  const [unlocked, setUnlocked] = useState(() => gateIsValid(NET_GATE_KEY))
  const { data: health } = useApi('/api/unifi/health', 30000)
  const { data: devices } = useApi('/api/unifi/devices', 60000)
  const { data: clients } = useApi('/api/unifi/clients', 60000)
  const { data: alarms } = useApi('/api/unifi/alarms', 60000)

  const subsystems = health?.subsystems || {}

  return (
    <div className="net-root gate-locked-wrapper">
      {!unlocked && (
        <div className="gate-locked-overlay">
          <GateUnlock
            storageKey={NET_GATE_KEY}
            label="Network operations data requires credentials:"
            onUnlock={() => setUnlocked(true)}
          />
        </div>
      )}
      <div className={unlocked ? '' : 'gate-content-blur'}>
        {unlocked && <GateSessionBar gateKey={NET_GATE_KEY} onLock={() => setUnlocked(false)} />}
        <AlarmsPanel alarms={alarms} />
        <StatusRail subsystems={subsystems} />
        <VitalsBar health={health} devices={devices} clients={clients} />
        <div className="net-main-grid">
          <InfraColumn devices={devices} />
          <WirelessColumn aps={devices?.aps} clients={clients} />
          <IntelligenceColumn clients={clients} devices={devices} />
        </div>
      </div>
    </div>
  )
}
