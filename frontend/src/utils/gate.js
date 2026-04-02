const TTL = 30 * 60 * 1000  // 30 minutes
export const TOKEN_KEY = 'security_gate_token'

export function gateIsValid(key) {
  const raw = sessionStorage.getItem(key)
  if (!raw) return false
  try {
    const { expires } = JSON.parse(raw)
    return typeof expires === 'number' && Date.now() < expires
  } catch {
    return false
  }
}

export function gateSet(key, code = null) {
  sessionStorage.setItem(key, JSON.stringify({ expires: Date.now() + TTL }))
  if (code !== null) sessionStorage.setItem(TOKEN_KEY, code)
}

export function gateClear(key) {
  sessionStorage.removeItem(key)
  sessionStorage.removeItem(TOKEN_KEY)
}

export function gateExpiresIn(key) {
  const raw = sessionStorage.getItem(key)
  if (!raw) return 0
  try {
    const { expires } = JSON.parse(raw)
    return Math.max(0, Math.round((expires - Date.now()) / 60000))
  } catch { return 0 }
}
