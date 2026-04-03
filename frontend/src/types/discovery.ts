// ── Discovery API types ───────────────────────────────────────────────────────
// These mirror the Python DiscoveryResult dataclass and run_scan() return shape.
// Any change to backend/services/environment_scan.py must be reflected here.

export type DiscoveryStatus = 'found' | 'not_found' | 'partial' | 'already_configured'
export type DiscoveryCategory = 'config' | 'gateway' | 'network' | 'local'

export interface DiscoveryResult {
  name: string
  status: DiscoveryStatus
  detail: string
  ip: string
  port: number
  env_keys: string[]
  suggested_values: Record<string, string>
  setup_hint: string
  category: DiscoveryCategory
}

export interface ScanResponse {
  status: 'complete' | 'running' | 'none'
  config: DiscoveryResult[]
  gateway: DiscoveryResult[]
  network: DiscoveryResult[]
  gateway_ip: string | null
  scan_duration_seconds: number
  scanned_at: number
  message?: string
}

export interface ConfigUpdateResponse {
  status: 'ok'
  message: string
  writable: boolean
}

// ── UI-only types ─────────────────────────────────────────────────────────────

export interface StatusDisplay {
  label: string
  className: string
}

export interface SaveState {
  saving: boolean
  saved: boolean
  error: string | null
}
