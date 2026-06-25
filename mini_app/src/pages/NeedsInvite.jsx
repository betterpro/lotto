import { useState } from 'react'
import { LOGO_SRC } from '../brand.js'
import { api } from '../api.js'

export default function NeedsInvite({ error, onJoined }) {
  const [tab, setTab] = useState('join') // 'join' | 'create'
  const [code, setCode] = useState('')
  const [groupName, setGroupName] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function joinByCode(e) {
    e.preventDefault()
    if (!code.trim()) return
    setErr(''); setBusy(true)
    try {
      await api.group.joinByCode(code.trim())
      onJoined?.()
    } catch (e2) {
      setErr(e2.message || 'Could not join group')
    } finally {
      setBusy(false)
    }
  }

  async function createGroup(e) {
    e.preventDefault()
    if (!groupName.trim()) return
    setErr(''); setBusy(true)
    try {
      await api.groups.create(groupName.trim())
      onJoined?.()
    } catch (e2) {
      setErr(e2.message || 'Could not create group')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-screen" style={{ gap: 16 }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ height: 56, objectFit: 'contain' }} />
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>
        {tab === 'join' ? 'Join your group' : 'Create your group'}
      </h2>

      {/* Tab switch */}
      <div style={{ display: 'flex', gap: 6, background: 'var(--bg-2, #f0f0f3)', padding: 4, borderRadius: 12 }}>
        {[['join', 'Join with code'], ['create', 'Create a group']].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => { setErr(''); setTab(key) }}
            style={{
              padding: '8px 14px', borderRadius: 9, border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 600,
              background: tab === key ? 'var(--surface, #fff)' : 'transparent',
              color: tab === key ? 'var(--tx-1, #111)' : 'var(--tx-3, #888)',
              boxShadow: tab === key ? '0 1px 3px rgba(0,0,0,.12)' : 'none',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'join' ? (
        <form onSubmit={joinByCode} style={{ width: '100%', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.6, margin: 0, textAlign: 'center' }}>
            Ask your trustee for the group join code, then enter it below.
          </p>
          <input
            type="text" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
            placeholder="ENTER CODE" value={code} maxLength={12}
            onChange={e => setCode(e.target.value.toUpperCase())}
            style={{
              padding: '14px 16px', fontSize: 22, fontWeight: 700, letterSpacing: 6,
              textAlign: 'center', borderRadius: 14, border: '1px solid var(--bd, #ddd)',
              outline: 'none', width: '100%', boxSizing: 'border-box', textTransform: 'uppercase',
            }}
          />
          {(err || error) && <span style={{ fontSize: 13, color: 'var(--danger)', lineHeight: 1.5 }}>{err || error}</span>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !code.trim()}>
            {busy ? 'Joining…' : 'Join group'}
          </button>
        </form>
      ) : (
        <form onSubmit={createGroup} style={{ width: '100%', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.6, margin: 0, textAlign: 'center' }}>
            Start your own group and become its trustee — open rounds, approve deposits, and invite
            friends with a join code.
          </p>
          <input
            type="text" placeholder="Your group name" value={groupName} maxLength={60}
            onChange={e => setGroupName(e.target.value)}
            style={{
              padding: '14px 16px', fontSize: 16, borderRadius: 14, border: '1px solid var(--bd, #ddd)',
              outline: 'none', width: '100%', boxSizing: 'border-box', textAlign: 'center',
            }}
          />
          {err && <span style={{ fontSize: 13, color: 'var(--danger)', lineHeight: 1.5 }}>{err}</span>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !groupName.trim()}>
            {busy ? 'Creating…' : 'Create group'}
          </button>
        </form>
      )}
    </div>
  )
}
