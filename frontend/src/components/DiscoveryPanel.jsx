import React, { useState } from 'react'

const STATUS_CONFIG = {
  found:              { label: 'Found',       cls: 'disc-found' },
  already_configured: { label: 'Configured',  cls: 'disc-configured' },
  not_found:          { label: 'Not Found',   cls: 'disc-missing' },
  partial:            { label: 'Partial',     cls: 'disc-partial' },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.not_found
  return <span className={`disc-badge ${cfg.cls}`}>{cfg.label}</span>
}

function ResultCard({ result, onSave, gateToken }) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [editValues, setEditValues] = useState(result.suggested_values || {})

  const canSave = result.status === 'found' &&
    result.env_keys.length > 0 &&
    Object.keys(editValues).length > 0

  async function handleSave() {
    if (!gateToken) return
    setSaving(true)
    setSaveError(null)
    try {
      const r = await fetch('/api/config/update', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Gate-Token': gateToken,
        },
        body: JSON.stringify({ updates: editValues }),
      })
      const d = await r.json()
      if (r.ok) {
        setSaved(true)
        if (onSave) onSave(d.message)
      } else {
        setSaveError(d.detail || 'Save failed')
      }
    } catch (e) {
      setSaveError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`disc-card ${result.status === 'already_configured' ? 'disc-card-dim' : ''}`}>
      <div className="disc-card-header">
        <span className="disc-card-name">{result.name}</span>
        <StatusBadge status={result.status} />
        {result.ip && <span className="disc-card-ip">{result.ip}{result.port ? `:${result.port}` : ''}</span>}
      </div>
      <div className="disc-card-detail">{result.detail}</div>
      {result.setup_hint && result.status !== 'already_configured' && (
        <div className="disc-card-hint">{result.setup_hint}</div>
      )}

      {canSave && !saved && (
        <div className="disc-card-save">
          {Object.entries(editValues).map(([k, v]) => (
            <div key={k} className="disc-env-row">
              <span className="disc-env-key">{k}</span>
              <input
                className="disc-env-val"
                value={v}
                onChange={e => setEditValues(prev => ({ ...prev, [k]: e.target.value }))}
                placeholder="value"
              />
            </div>
          ))}
          {result.env_keys.filter(k => !editValues[k]).map(k => (
            <div key={k} className="disc-env-row">
              <span className="disc-env-key">{k}</span>
              <input
                className="disc-env-val"
                value=""
                onChange={e => setEditValues(prev => ({ ...prev, [k]: e.target.value }))}
                placeholder="enter value..."
              />
            </div>
          ))}
          <button
            className="disc-save-btn"
            onClick={handleSave}
            disabled={saving || !gateToken}
          >
            {saving ? 'Saving…' : gateToken ? 'Save to .env' : 'Unlock to save'}
          </button>
        </div>
      )}
      {saveError && <div className="disc-error" style={{marginTop:'0.4rem'}}>{saveError}</div>}
      {saved && <div className="disc-saved">✓ Saved — restart container to apply</div>}
    </div>
  )
}

function Section({ title, icon, results, onSave, gateToken }) {
  if (!results || results.length === 0) return null
  return (
    <div className="disc-section">
      <div className="disc-section-header">{icon} {title}</div>
      <div className="disc-cards">
        {results.map((r, i) => (
          <ResultCard key={r.name || i} result={r} onSave={onSave} gateToken={gateToken} />
        ))}
      </div>
    </div>
  )
}

export default function DiscoveryPanel({ gateToken }) {
  const [scanning, setScanning] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [saveMsg, setSaveMsg] = useState(null)
  const [includeSubnet, setIncludeSubnet] = useState(true)

  async function runScan() {
    setScanning(true)
    setError(null)
    setSaveMsg(null)
    try {
      const r = await fetch(`/api/discovery/scan?include_subnet=${includeSubnet}`, { method: 'POST' })
      const d = await r.json()
      if (r.ok) {
        setResults(d)
      } else {
        setError(d.detail || 'Scan failed')
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setScanning(false)
    }
  }

  const foundCount = results
    ? [...(results.gateway || []), ...(results.network || [])].filter(r => r.status === 'found').length
    : 0

  const unconfigured = results
    ? (results.config || []).filter(r => r.status === 'not_found').length
    : 0

  return (
    <div className="disc-panel">
      <div className="disc-panel-header">
        <div>
          <h3>Environment Discovery</h3>
          <p className="disc-intro">
            Scan your network to find services you can add to this dashboard.
            {!gateToken && ' Unlock the session to save discovered settings to your .env.'}
          </p>
        </div>
        <div className="disc-controls">
          <label className="disc-toggle">
            <input
              type="checkbox"
              checked={includeSubnet}
              onChange={e => setIncludeSubnet(e.target.checked)}
              disabled={scanning}
            />
            <span>Subnet sweep</span>
            {includeSubnet && <span className="disc-warn">~30–60s</span>}
          </label>
          <button className="disc-run-btn" onClick={runScan} disabled={scanning}>
            {scanning ? (
              <><span className="disc-spinner" /> Scanning…</>
            ) : (
              results ? 'Re-scan' : 'Scan Environment'
            )}
          </button>
        </div>
      </div>

      {error && <div className="disc-error">{error}</div>}
      {saveMsg && <div className="disc-save-notice">{saveMsg}</div>}

      {results && (
        <>
          <div className="disc-summary">
            Scan completed in {results.scan_duration_seconds}s
            {results.gateway_ip && ` · Gateway: ${results.gateway_ip}`}
            {foundCount > 0 && ` · ${foundCount} new service${foundCount !== 1 ? 's' : ''} found`}
            {unconfigured > 0 && ` · ${unconfigured} integration${unconfigured !== 1 ? 's' : ''} not configured`}
          </div>

          <Section
            title="Current Configuration"
            icon="⬡"
            results={results.config}
            onSave={setSaveMsg}
            gateToken={gateToken}
          />
          <Section
            title="Gateway / Router"
            icon="◈"
            results={results.gateway}
            onSave={setSaveMsg}
            gateToken={gateToken}
          />
          <Section
            title="Network Services"
            icon="◉"
            results={results.network}
            onSave={setSaveMsg}
            gateToken={gateToken}
          />
        </>
      )}

      {!results && !scanning && (
        <div className="disc-empty">
          Run a scan to discover what integrations are available in your environment.
        </div>
      )}
    </div>
  )
}
