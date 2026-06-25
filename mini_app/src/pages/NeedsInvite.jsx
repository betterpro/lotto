import { useState } from 'react'
import { LOGO_SRC } from '../brand.js'
import { api } from '../api.js'

export default function NeedsInvite({ error, onJoined }) {
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (!code.trim()) return
    setErr('')
    setBusy(true)
    try {
      await api.group.joinByCode(code.trim())
      onJoined?.()
    } catch (e2) {
      setErr(e2.message || 'Could not join group')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="center-screen" style={{ gap: 18 }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ height: 56, objectFit: 'contain' }} />
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Join your group</h2>
      <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, maxWidth: 320, margin: 0 }}>
        Ask your trustee for the group join code, then enter it below.
      </p>

      <form onSubmit={submit} style={{ width: '100%', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <input
          type="text"
          inputMode="text"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
          placeholder="ENTER CODE"
          value={code}
          onChange={e => setCode(e.target.value.toUpperCase())}
          maxLength={12}
          style={{
            padding: '14px 16px', fontSize: 22, fontWeight: 700, letterSpacing: 6,
            textAlign: 'center', borderRadius: 14, border: '1px solid var(--bd, #ddd)',
            outline: 'none', width: '100%', boxSizing: 'border-box', textTransform: 'uppercase',
          }}
        />
        {(err || error) && (
          <span style={{ fontSize: 13, color: 'var(--danger)', lineHeight: 1.5 }}>{err || error}</span>
        )}
        <button type="submit" className="btn btn-primary btn-block" disabled={busy || !code.trim()}>
          {busy ? 'Joining…' : 'Join group'}
        </button>
      </form>

      <p style={{ fontSize: 12, color: 'var(--tx-3)', margin: 0, maxWidth: 300, lineHeight: 1.5 }}>
        Don’t have a code? Your trustee can find it on their Home screen under “Invite friends”.
      </p>
    </div>
  )
}
