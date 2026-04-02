import React, { useState, useEffect } from 'react'
import { gateClear, gateExpiresIn } from '../utils/gate'

export default function GateSessionBar({ gateKey, onLock }) {
  const [mins, setMins] = useState(() => gateExpiresIn(gateKey))

  useEffect(() => {
    const id = setInterval(() => {
      const remaining = gateExpiresIn(gateKey)
      setMins(remaining)
      if (remaining <= 0) onLock()
    }, 30000)
    return () => clearInterval(id)
  }, [gateKey, onLock])

  return (
    <div className="gate-session-bar">
      <span className="gate-session-dot" />
      <span className="gate-session-label">Session unlocked · {mins}m remaining</span>
      <button
        className="gate-lock-btn"
        onClick={() => { gateClear(gateKey); onLock() }}
      >
        Lock
      </button>
    </div>
  )
}
