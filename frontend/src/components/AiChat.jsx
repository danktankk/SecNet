import React, { useState, useRef, useEffect } from 'react'
import { gateIsValid, gateSet, TOKEN_KEY } from '../utils/gate'

const GATE_KEY = 'security_gate_chat'

const EXAMPLE_GROUPS = [
  {
    label: 'Safe to ask (no auth)',
    questions: [
      'What does threat level mean?',
      'How does CrowdSec work?',
      'Explain what a firewall ban does',
      'What is the difference between a block and a ban?',
    ],
  },
  {
    label: 'Requires auth (sensitive)',
    questions: [
      'What are the current active bans?',
      'Which countries are attacking the network?',
      'Are there any suspicious open ports?',
      'Show me recent lateral movement activity',
    ],
  },
]

export default function AiChat() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [unlocked, setUnlocked] = useState(() => gateIsValid(GATE_KEY))
  const [showGatePrompt, setShowGatePrompt] = useState(false)
  const [gateInput, setGateInput] = useState('')
  const [gateError, setGateError] = useState('')
  const [showExamples, setShowExamples] = useState(true)
  const messagesRef = useRef(null)
  const pendingQuestion = useRef(null)

  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages, loading])

  const submitGate = async () => {
    setGateError('')
    try {
      const r = await fetch('/api/chat/gate-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: gateInput }),
      })
      if (r.status === 429) {
        setGateError('Too many attempts. Please wait a minute before trying again.')
        return
      }
      const d = await r.json()
      if (d.unlocked) {
        gateSet(GATE_KEY, gateInput)
        setUnlocked(true)
        setShowGatePrompt(false)
        setGateInput('')
        setMessages(prev => [...prev, { role: 'assistant', content: 'Credentials verified — re-sending your question…' }])
        // Re-send the question that triggered the gate
        if (pendingQuestion.current) {
          const q = pendingQuestion.current
          pendingQuestion.current = null
          setTimeout(() => sendWithUnlocked(q), 300)
        }
      } else {
        setGateError('Invalid credentials.')
        setGateInput('')
      }
    } catch {
      setGateError('Authentication service unavailable.')
    }
  }

  const sendWithUnlocked = async (msg) => {
    setMessages(prev => {
      const newMessages = [...prev, { role: 'user', content: msg }]
      doSend(newMessages)
      return newMessages
    })
  }

  const doSend = async (messageHistory) => {
    setLoading(true)
    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Gate-Token': sessionStorage.getItem(TOKEN_KEY) || '',
        },
        body: JSON.stringify({
          messages: messageHistory.map(m => ({ role: m.role, content: m.content })),
        }),
      })
      if (!r.ok) {
        const errText = await r.text().catch(() => r.statusText)
        setMessages(prev => [...prev, { role: 'assistant', content: `AI service error (${r.status}): ${errText}` }])
        setLoading(false)
        return
      }
      const data = await r.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])

      if (data.reply && data.reply.includes('requires authentication') && !unlocked) {
        setShowGatePrompt(true)
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error connecting to AI service: ${err.message}` }])
    }
    setLoading(false)
  }

  const send = async (text) => {
    const msg = (text || input).trim()
    if (!msg || loading) return
    setInput('')

    const newMessages = [...messages, { role: 'user', content: msg }]
    setMessages(newMessages)
    setLoading(true)

    try {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Gate-Token': sessionStorage.getItem(TOKEN_KEY) || '',
        },
        body: JSON.stringify({
          messages: newMessages.map(m => ({ role: m.role, content: m.content })),
        }),
      })
      if (!r.ok) {
        const errText = await r.text().catch(() => r.statusText)
        setMessages(prev => [...prev, { role: 'assistant', content: `AI service error (${r.status}): ${errText}` }])
        setLoading(false)
        return
      }
      const data = await r.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.reply }])

      if (data.reply && data.reply.includes('requires authentication') && !unlocked) {
        pendingQuestion.current = msg   // save for re-send after auth
        setShowGatePrompt(true)
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error connecting to AI service: ${err.message}` }])
    }
    setLoading(false)
  }

  return (
    <div className="ai-chat-wrapper">
      <button className="ai-chat-toggle" onClick={() => setOpen(!open)}>
        {open ? '▼' : '▶'} HelpDesk
      </button>
      {open && (
        <div className="ai-chat-panel">
          <div className="ai-chat-messages" ref={messagesRef}>
            {messages.length === 0 && (
              <div className="ai-chat-hint">Ask about threats, bans, device status, VLANs, AP health, or network topology. Sensitive data requires auth. No access to external systems or real-time data outside this dashboard.</div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`ai-msg ai-msg-${m.role}`}>
                <span className="ai-msg-role">{m.role === 'user' ? 'User' : 'AI'}</span>
                <span className="ai-msg-text">{m.content}</span>
              </div>
            ))}
            {loading && <div className="ai-msg ai-msg-assistant"><span className="ai-msg-role">AI</span><span className="ai-msg-text ai-typing">Thinking…</span></div>}
            {showGatePrompt && !unlocked && (
              <div className="gate-prompt">
                <div className="gate-label">Enter credentials to access sensitive data:</div>
                <div className="gate-input-row">
                  <input
                    type="password"
                    value={gateInput}
                    onChange={e => setGateInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && submitGate()}
                    placeholder="Credentials"
                    autoFocus
                  />
                  <button onClick={submitGate}>Authenticate</button>
                </div>
                {gateError && <div className="gate-error">{gateError}</div>}
              </div>
            )}
          </div>

          <div className="ai-examples-bar">
            <button className="ai-examples-toggle" onClick={() => setShowExamples(v => !v)}>
              Examples {showExamples ? '▲ (click to close)' : '▼'}
            </button>
          </div>
          {showExamples && (
            <div className="ai-examples-panel">
              {EXAMPLE_GROUPS.map(g => (
                <div key={g.label} className="ai-example-group">
                  <div className="ai-example-label">{g.label}</div>
                  <div className="ai-example-chips">
                    {g.questions.map(q => (
                      <button key={q} className="ai-example-chip" onClick={() => send(q)}>{q}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="ai-chat-input">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Ask a question…"
              disabled={loading}
            />
            <button onClick={() => send()} disabled={loading}>Send</button>
          </div>
        </div>
      )}
    </div>
  )
}
