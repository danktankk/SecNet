/**
 * Shared formatting utilities used across dashboard components.
 */

/** Format bytes as a rate string (e.g., "1.2 MB/s") */
export function fmtBytesRate(b) {
  if (!b) return '0 B/s'
  if (b < 1024) return b + ' B/s'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB/s'
  return (b / 1048576).toFixed(1) + ' MB/s'
}

/** Format bytes as a total (e.g., "1.2 GB") */
export function fmtBytes(b) {
  if (!b) return '0 B'
  if (b < 1024) return b + ' B'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'
  if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB'
  return (b / 1073741824).toFixed(1) + ' GB'
}

/** Format seconds to human-readable uptime (e.g., "3d 4h" or "2h 15m") */
export function fmtUptime(s) {
  if (!s) return '--'
  const h = Math.floor(s / 3600)
  const d = Math.floor(h / 24)
  if (d > 0) return `${d}d ${h % 24}h`
  return `${h}h ${Math.floor((s % 3600) / 60)}m`
}

/** Format bytes to memory string (e.g., "512 MB" or "4.0 GB") */
export function fmtMem(bytes) {
  if (!bytes) return '0 B'
  if (bytes < 1073741824) return (bytes / 1048576).toFixed(0) + ' MB'
  return (bytes / 1073741824).toFixed(1) + ' GB'
}
