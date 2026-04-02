import React, { useState } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts'

export default function Timeline({ data }) {
  const [view, setView] = useState('bans')

  if (!data || !data.length) return <div className="loading">Loading timeline…</div>

  const formatted = data.map(d => ({
    ...d,
    time: new Date(d.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  }))

  const hasActivity = formatted.some(d => d.bucket_events > 0 || d.parser_hits > 0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
        {[
          { id: 'bans', label: 'Ban Count' },
          { id: 'activity', label: 'Event Rate' },
        ].map(v => (
          <button
            key={v.id}
            onClick={() => setView(v.id)}
            style={{
              padding: '3px 10px', fontSize: '0.72rem', border: '1px solid var(--border)',
              borderRadius: 4, cursor: 'pointer', fontWeight: 600,
              background: view === v.id ? 'var(--bg-card-hover)' : 'transparent',
              color: view === v.id ? 'var(--blue)' : 'var(--text-muted)',
              borderColor: view === v.id ? 'var(--blue)' : 'var(--border)',
            }}
          >{v.label}</button>
        ))}
      </div>

      {view === 'bans' && (
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart data={formatted}>
            <defs>
              <linearGradient id="gBans" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#00ff87" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#00ff87" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="time" tick={{ fill: '#8b949e', fontSize: 10 }} interval={23} />
            <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} tickFormatter={v => (v/1000).toFixed(0)+'k'} />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e6edf3', fontSize: 12 }}
              formatter={(v) => [v.toLocaleString(), 'Active Bans']}
            />
            <Area type="monotone" dataKey="bans" stroke="#00ff87" fill="url(#gBans)" dot={false} strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
      )}

      {view === 'activity' && (
        <ResponsiveContainer width="100%" height={230}>
          <AreaChart data={formatted}>
            <defs>
              <linearGradient id="gBuckets" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ffb700" stopOpacity={0.4} />
                <stop offset="95%" stopColor="#ffb700" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gParser" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#58a6ff" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#58a6ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="time" tick={{ fill: '#8b949e', fontSize: 10 }} interval={23} />
            <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, color: '#e6edf3', fontSize: 12 }}
            />
            <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e' }} />
            <Area type="monotone" dataKey="bucket_events" name="Bucket Events" stroke="#ffb700" fill="url(#gBuckets)" dot={false} strokeWidth={1.5} />
            <Area type="monotone" dataKey="parser_hits" name="Log Lines" stroke="#58a6ff" fill="url(#gParser)" dot={false} strokeWidth={1} />
          </AreaChart>
        </ResponsiveContainer>
      )}

      {view === 'activity' && !hasActivity && (
        <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textAlign: 'center', marginTop: -180 }}>
          Low event rate — activity spikes will appear here when triggered
        </div>
      )}
    </div>
  )
}
