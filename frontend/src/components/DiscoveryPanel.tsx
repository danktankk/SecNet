import React, { useState } from 'react'
import type {
  DiscoveryResult,
  DiscoveryStatus,
  ScanResponse,
  ConfigUpdateResponse,
  StatusDisplay,
  SaveState,
} from '../types/discovery'

// ── Static config (module scope, never rebuilt) ───────────────────────────────

const STATUS_DISPLAY: Record<DiscoveryStatus, StatusDisplay> = {
  found:              { label: 'Found',      className: 'disc-found' },
  already_configured: { label: 'Configured', className: 'disc-configured' },
  not_found:          { label: 'Not Found',  className: 'disc-missing' },
  partial:            { label: 'Partial',    className: 'disc-partial' },
}

const DEFAULT_SAVE_STATE: SaveState = { saving: false, saved: false, error: null }

// ── Pure data functions (no JSX) ──────────────────────────────────────────────

function getStatusDisplay(status: DiscoveryStatus): StatusDisplay {
  return STATUS_DISPLAY[status] ?? STATUS_DISPLAY.not_found
}

function canSave(result: DiscoveryResult, saved: boolean): boolean {
  return (
    !saved &&
    result.status === 'found' &&
    result.env_keys.length > 0
  )
}

function countFound(results: ScanResponse): number {
  return [...results.gateway, ...results.network].filter(r => r.status === 'found').length
}

function countUnconfigured(results: ScanResponse): number {
  return results.config.filter(r => r.status === 'not_found').length
}

function buildScanSummary(results: ScanResponse): string {
  const parts: string[] = [`Scan completed in ${results.scan_duration_seconds}s`]
  if (results.gateway_ip) parts.push(`Gateway: ${results.gateway_ip}`)
  const found = countFound(results)
  if (found > 0) parts.push(`${found} new service${found !== 1 ? 's' : ''} found`)
  const unconfigured = countUnconfigured(results)
  if (unconfigured > 0) parts.push(`${unconfigured} integration${unconfigured !== 1 ? 's' : ''} not configured`)
  return parts.join(' · ')
}

async function postConfigUpdate(
  updates: Record<string, string>,
  gateToken: string,
): Promise<ConfigUpdateResponse> {
  const res = await fetch('/api/config/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Gate-Token': gateToken },
    body: JSON.stringify({ updates }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Save failed' }))
    throw new Error((err as { detail?: string }).detail ?? 'Save failed')
  }
  return res.json() as Promise<ConfigUpdateResponse>
}

async function postScan(includeSubnet: boolean): Promise<ScanResponse> {
  const res = await fetch(`/api/discovery/scan?include_subnet=${includeSubnet}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Scan failed' }))
    throw new Error((err as { detail?: string }).detail ?? 'Scan failed')
  }
  return res.json() as Promise<ScanResponse>
}

// ── Component prop interfaces ─────────────────────────────────────────────────

interface StatusBadgeProps {
  status: DiscoveryStatus
}

interface ResultCardProps {
  result: DiscoveryResult
  gateToken: string
  onSaved: (message: string) => void
}

interface SectionProps {
  title: string
  icon: string
  results: DiscoveryResult[]
  gateToken: string
  onSaved: (message: string) => void
}

interface DiscoveryPanelProps {
  gateToken: string
}

// ── Components ────────────────────────────────────────────────────────────────

const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const { label, className } = getStatusDisplay(status)
  return <span className={`disc-badge ${className}`}>{label}</span>
}

const ResultCard: React.FC<ResultCardProps> = ({ result, gateToken, onSaved }) => {
  const [saveState, setSaveState] = useState<SaveState>(DEFAULT_SAVE_STATE)
  const [editValues, setEditValues] = useState<Record<string, string>>(result.suggested_values ?? {})

  const showSaveForm = canSave(result, saveState.saved)
  const missingKeys = result.env_keys.filter(k => !editValues[k])

  async function handleSave(): Promise<void> {
    if (!gateToken) return
    setSaveState({ saving: true, saved: false, error: null })
    try {
      const data = await postConfigUpdate(editValues, gateToken)
      setSaveState({ saving: false, saved: true, error: null })
      onSaved(data.message)
    } catch (err) {
      setSaveState({ saving: false, saved: false, error: String(err instanceof Error ? err.message : err) })
    }
  }

  function handleValueChange(key: string, value: string): void {
    setEditValues(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className={`disc-card${result.status === 'already_configured' ? ' disc-card-dim' : ''}`}>
      <div className="disc-card-header">
        <span className="disc-card-name">{result.name}</span>
        <StatusBadge status={result.status} />
        {result.ip && <span className="disc-card-ip">{result.ip}{result.port ? `:${result.port}` : ''}</span>}
      </div>

      {result.detail && <div className="disc-card-detail">{result.detail}</div>}
      {result.setup_hint && result.status !== 'already_configured' && (
        <div className="disc-card-hint">{result.setup_hint}</div>
      )}

      {showSaveForm && (
        <div className="disc-card-save">
          {Object.entries(editValues).map(([k, v]) => (
            <div key={k} className="disc-env-row">
              <span className="disc-env-key">{k}</span>
              <input
                className="disc-env-val"
                value={v}
                onChange={e => handleValueChange(k, e.target.value)}
                placeholder="value"
              />
            </div>
          ))}
          {missingKeys.map(k => (
            <div key={k} className="disc-env-row">
              <span className="disc-env-key">{k}</span>
              <input
                className="disc-env-val"
                onChange={e => handleValueChange(k, e.target.value)}
                placeholder="enter value…"
              />
            </div>
          ))}
          <button className="disc-save-btn" onClick={handleSave} disabled={saveState.saving || !gateToken}>
            {saveState.saving ? 'Saving…' : gateToken ? 'Save to .env' : 'Unlock to save'}
          </button>
          {saveState.error && <div className="disc-card-error">{saveState.error}</div>}
        </div>
      )}

      {saveState.saved && <div className="disc-saved">✓ Saved — restart container to apply</div>}
    </div>
  )
}

const Section: React.FC<SectionProps> = ({ title, icon, results, gateToken, onSaved }) => {
  if (!results.length) return null
  return (
    <div className="disc-section">
      <div className="disc-section-header">{icon} {title}</div>
      <div className="disc-cards">
        {results.map(r => (
          <ResultCard key={r.name} result={r} gateToken={gateToken} onSaved={onSaved} />
        ))}
      </div>
    </div>
  )
}

export default function DiscoveryPanel({ gateToken }: DiscoveryPanelProps): React.ReactElement {
  const [scanning, setScanning] = useState(false)
  const [results, setResults] = useState<ScanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saveNotice, setSaveNotice] = useState<string | null>(null)
  const [includeSubnet, setIncludeSubnet] = useState(true)

  async function runScan(): Promise<void> {
    setScanning(true)
    setError(null)
    setSaveNotice(null)
    try {
      const data = await postScan(includeSubnet)
      setResults(data)
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err))
    } finally {
      setScanning(false)
    }
  }

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
            {scanning ? <><span className="disc-spinner" /> Scanning…</> : results ? 'Re-scan' : 'Scan Environment'}
          </button>
        </div>
      </div>

      {error && <div className="disc-error">{error}</div>}
      {saveNotice && <div className="disc-save-notice">{saveNotice}</div>}

      {results && (
        <>
          <div className="disc-summary">{buildScanSummary(results)}</div>
          <Section title="Current Configuration" icon="⬡" results={results.config} gateToken={gateToken} onSaved={setSaveNotice} />
          <Section title="Gateway / Router"       icon="◈" results={results.gateway} gateToken={gateToken} onSaved={setSaveNotice} />
          <Section title="Network Services"       icon="◉" results={results.network} gateToken={gateToken} onSaved={setSaveNotice} />
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
