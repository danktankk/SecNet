import React, { useState } from 'react'
import { gateSet } from '../utils/gate'

export default function GateUnlock({ storageKey, label = 'Enter credentials:', onUnlock }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState('')

  const submit = async () => {
    setError('')
    try {
      const r = await fetch('/api/chat/gate-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: code }),
      })
      const d = await r.json()
      if (d.unlocked) {
        if (storageKey) gateSet(storageKey, code)  // store expiry + actual code for API calls
        onUnlock()
      } else {
        setError('Invalid credentials.')
        setCode('')
      }
    } catch {
      setError('Service unavailable.')
    }
  }

  return (
    <div className="gate-inline">
      <span className="gate-inline-label">{label}</span>
      <input type="password" value={code} onChange={e => setCode(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && submit()} placeholder="Credentials" />
      <button onClick={submit}>Unlock</button>
      {error && <span className="gate-error">{error}</span>}
    </div>
  )
}
