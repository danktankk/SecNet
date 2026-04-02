import { useState, useEffect, useCallback, useRef } from 'react'

const CACHE_PREFIX = 'apicache_'
const MAX_CACHE_BYTES = 400_000  // skip caching responses larger than 400KB

function readCache(url) {
  try {
    const raw = localStorage.getItem(CACHE_PREFIX + url)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function writeCache(url, data) {
  try {
    const serialized = JSON.stringify(data)
    if (serialized.length > MAX_CACHE_BYTES) return
    localStorage.setItem(CACHE_PREFIX + url, serialized)
  } catch {} // quota exceeded — silently skip
}

export function useApi(url, interval = 30000) {
  const cached = readCache(url)
  const [data, setData] = useState(cached)
  const [loading, setLoading] = useState(cached === null)  // only show loading state on first-ever load
  const [refreshing, setRefreshing] = useState(false)
  const hasData = useRef(cached !== null)

  const fetch_ = useCallback(async () => {
    if (hasData.current) setRefreshing(true)
    try {
      const r = await fetch(url)
      if (r.ok) {
        const d = await r.json()
        setData(d)
        hasData.current = true
        writeCache(url, d)
      }
    } catch (e) { /* silent */ }
    setLoading(false)
    setRefreshing(false)
  }, [url])

  useEffect(() => {
    fetch_()
    if (interval > 0) {
      const id = setInterval(fetch_, interval)
      return () => clearInterval(id)
    }
  }, [fetch_, interval])

  return { data, loading, refreshing, refetch: fetch_ }
}

export function useWebSocket(url) {
  const [lastMessage, setLastMessage] = useState(null)

  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${proto}//${window.location.host}${url}`
    let ws = null
    let reconnectTimeout = null
    let backoff = 1000
    let cancelled = false

    function connect() {
      if (cancelled) return
      ws = new WebSocket(wsUrl)
      ws.onopen = () => { backoff = 1000 }
      ws.onmessage = (e) => { try { setLastMessage(JSON.parse(e.data)) } catch {} }
      ws.onclose = () => {
        if (!cancelled) {
          reconnectTimeout = setTimeout(connect, backoff)
          backoff = Math.min(backoff * 2, 30000)
        }
      }
    }
    connect()

    return () => {
      cancelled = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      if (ws) ws.close()
    }
  }, [url])

  return lastMessage
}
