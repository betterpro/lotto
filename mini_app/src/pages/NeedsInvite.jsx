import { useState, useEffect } from 'react'
import Logo from '../components/Logo.jsx'
import { api } from '../api.js'

export default function NeedsInvite({ error, onJoined }) {
  const [tab, setTab] = useState('join') // 'join' | 'request'
  const [code, setCode] = useState('')
  const [groupName, setGroupName] = useState('')
  const [plan, setPlan] = useState('subscription')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [application, setApplication] = useState(null)

  useEffect(() => {
    api.trustee.application().then(r => setApplication(r.application)).catch(() => {})
  }, [])

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

  async function requestGroup(e) {
    e.preventDefault()
    if (!groupName.trim()) return
    setErr(''); setBusy(true)
    try {
      await api.trustee.apply(groupName.trim(), plan)
      const r = await api.trustee.application()
      setApplication(r.application)
      setGroupName('')
    } catch (e2) {
      setErr(e2.message || 'Could not submit request')
    } finally {
      setBusy(false)
    }
  }

  const pending = application?.status === 'pending'

  return (
    <div className="center-screen" style={{ gap: 16 }}>
      <Logo size={46} wordmark fontSize={30} />
      <h2 style={{ fontSize: 21, fontWeight: 700, margin: 0 }}>
        {tab === 'join' ? 'Join your group' : 'Start your own group'}
      </h2>

      {/* Tab switch */}
      <div style={{ display: 'flex', gap: 6, background: 'var(--bg-2, #f0f0f3)', padding: 4, borderRadius: 12 }}>
        {[['join', 'Join with code'], ['request', 'Start a group']].map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => { setErr(''); setTab(key) }}
            style={{
              padding: '8px 14px', borderRadius: 9, border: 'none', cursor: 'pointer',
              fontSize: 14, fontWeight: 600,
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
          <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, margin: 0, textAlign: 'center' }}>
            Ask your trustee for the group join code, then enter it below.
          </p>
          <input
            type="text" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
            placeholder="ENTER CODE" value={code} maxLength={12}
            onChange={e => setCode(e.target.value.toUpperCase())}
            style={{
              padding: '14px 16px', fontSize: 23, fontWeight: 700, letterSpacing: 6,
              textAlign: 'center', borderRadius: 14, border: '1px solid var(--bd, #ddd)',
              outline: 'none', width: '100%', boxSizing: 'border-box', textTransform: 'uppercase',
            }}
          />
          {(err || error) && <span style={{ fontSize: 14, color: 'var(--danger)', lineHeight: 1.5 }}>{err || error}</span>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !code.trim()}>
            {busy ? 'Joining…' : 'Join group'}
          </button>
        </form>
      ) : pending ? (
        <div style={{ width: '100%', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 8, textAlign: 'center' }}>
          <p style={{ fontSize: 15, color: 'var(--tx-1)', margin: 0, lineHeight: 1.6 }}>
            Your request for <strong>{application.proposed_group_name}</strong> is pending platform approval.
          </p>
          <p style={{ fontSize: 13, color: 'var(--tx-3)', margin: 0, lineHeight: 1.5 }}>
            We’ll set up your group once it’s approved. In the meantime you can join an existing
            group with a code.
          </p>
        </div>
      ) : (
        <form onSubmit={requestGroup} style={{ width: '100%', maxWidth: 300, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, margin: 0, textAlign: 'center' }}>
            Want to run your own pool? Request a group — once a platform admin approves it, you’ll
            become its trustee with your own join code.
          </p>
          {application?.status === 'rejected' && (
            <span style={{ fontSize: 13, color: 'var(--danger)', lineHeight: 1.5 }}>
              Previous request was rejected{application.review_notes ? `: ${application.review_notes}` : '.'}
            </span>
          )}
          <input
            type="text" placeholder="Your group name" value={groupName} maxLength={60}
            onChange={e => setGroupName(e.target.value)}
            style={{
              padding: '14px 16px', fontSize: 17, borderRadius: 14, border: '1px solid var(--bd, #ddd)',
              outline: 'none', width: '100%', boxSizing: 'border-box', textAlign: 'center',
            }}
          />
          <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, textTransform: 'uppercase',
            letterSpacing: '.4px', textAlign: 'left', marginTop: 2 }}>Choose your plan</div>
          {[
            { id: 'subscription', title: 'Monthly subscription', price: '$6.99/mo',
              desc: 'Flat fee. Keep 100% of every prize.' },
            { id: 'prize_share', title: 'Big-prize share', price: 'No monthly fee',
              desc: 'Platform may claim 5% of wins over $1,000.' },
          ].map(opt => {
            const on = plan === opt.id
            return (
              <button type="button" key={opt.id} onClick={() => setPlan(opt.id)}
                style={{
                  textAlign: 'left', padding: '12px 14px', borderRadius: 14, cursor: 'pointer',
                  background: on ? 'rgba(46,166,255,.12)' : 'var(--bg-3)',
                  border: `1.5px solid ${on ? 'var(--tg)' : 'var(--hairline-2, #34465A)'}`,
                }}>
                <div className="row between" style={{ alignItems: 'center' }}>
                  <span style={{ fontSize: 14, fontWeight: 700, color: on ? 'var(--tg)' : 'var(--tx-1)' }}>{opt.title}</span>
                  <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--money)' }}>{opt.price}</span>
                </div>
                <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 3, lineHeight: 1.4 }}>{opt.desc}</div>
              </button>
            )
          })}
          <span style={{ fontSize: 11, color: 'var(--tx-3)', lineHeight: 1.5 }}>
            Your plan is locked into the group agreement when approved and can’t be changed later.
          </span>
          {err && <span style={{ fontSize: 14, color: 'var(--danger)', lineHeight: 1.5 }}>{err}</span>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !groupName.trim()}>
            {busy ? 'Submitting…' : 'Request group'}
          </button>
        </form>
      )}
    </div>
  )
}
