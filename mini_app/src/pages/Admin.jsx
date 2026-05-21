import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

function StatusBadge({ s }) {
  const map = { open: ['bg-green', 'Open'], closed: ['bg-yellow', 'Closed'], drawn: ['bg-blue', 'Drawn'] }
  const [cls, label] = map[s] ?? ['bg-gray', s]
  return <span className={`badge ${cls}`}>{label}</span>
}

export default function Admin() {
  const [tab,        setTab]        = useState('round')
  const [round,      setRound]      = useState(undefined)
  const [deposits,   setDeposits]   = useState(null)
  const [members,    setMembers]    = useState(null)
  const [busy,       setBusy]       = useState({})
  const [toast,      setToast]      = useState(null)
  const [drawResult, setDrawResult] = useState(null)

  function showToast(msg, error = false) {
    setToast({ msg, error }); setTimeout(() => setToast(null), 4000)
  }

  const loadRound    = useCallback(() => api.admin.round().then(d => setRound(d.round)).catch(() => setRound(null)), [])
  const loadDeposits = useCallback(() => api.admin.deposits().then(d => setDeposits(d.deposits)).catch(() => setDeposits([])), [])
  const loadMembers  = useCallback(() => api.admin.members().then(d => setMembers(d.members)).catch(() => setMembers([])), [])

  useEffect(() => { loadRound(); loadDeposits(); loadMembers() }, [])

  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  async function roundAction(key, fn, label) {
    setB(key, true)
    try {
      const res = await fn()
      showToast(label(res))
      await loadRound()
      if (key === 'draw') setDrawResult(res)
    } catch (err) { showToast(err.message, true) }
    finally { setB(key, false) }
  }

  async function resolveDeposit(id, action) {
    setB(`d${id}`, true)
    try {
      await api.admin.resolve(id, action)
      showToast(action === 'approve' ? 'Deposit approved!' : 'Deposit rejected.')
      await loadDeposits()
    } catch (err) { showToast(err.message, true) }
    finally { setB(`d${id}`, false) }
  }

  function confirmDraw() {
    const tg = window.Telegram?.WebApp
    const run = () => roundAction('draw', api.admin.draw, r => `Winner: ${r.winner_name} — ${r.pool.toFixed(2)} USD`)
    if (tg?.showConfirm) tg.showConfirm('Draw a winner now? This cannot be undone.', ok => { if (ok) run() })
    else if (window.confirm('Draw a winner now? This cannot be undone.')) run()
  }

  const st = round?.status
  const canOpen  = !round || st === 'drawn'
  const canClose = st === 'open'
  const canDraw  = st === 'closed'

  return (
    <div className="page">
      {/* Tab bar */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['round', 'deposits', 'members'].map(t => (
          <button key={t} className={`btn btn-sm ${tab === t ? '' : 'btn-ghost'}`}
            onClick={() => setTab(t)}
            style={{ flex: 1, textTransform: 'capitalize', marginBottom: 0 }}>
            {t === 'deposits' && deposits?.length ? `Deps (${deposits.length})` : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Round tab */}
      {tab === 'round' && (
        <>
          {round && (
            <div className="card">
              <div className="row" style={{ marginBottom: 8 }}>
                <div className="card-label" style={{ marginBottom: 0 }}>Round #{round.id}</div>
                <StatusBadge s={round.status} />
              </div>
              <div className="big-num">{round.pool.toFixed(2)}</div>
              <div className="sub mt4">{round.participants.length} participant{round.participants.length !== 1 ? 's' : ''}</div>
              {round.participants.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  {round.participants.map(p => (
                    <div key={p.user_id} style={{ marginBottom: 10 }}>
                      <div className="row">
                        <span style={{ fontSize: 14 }}>{p.full_name}</span>
                        <span className="hint" style={{ fontSize: 13 }}>{p.pct}% · {p.amount.toFixed(2)}</span>
                      </div>
                      <div className="bar mt4">
                        <div className="bar-fill" style={{ width: `${p.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {drawResult && (
            <div className="card" style={{ border: '2px solid #f9a825' }}>
              <div className="card-label">🏆 Draw Result</div>
              <div style={{ fontWeight: 700, fontSize: 20 }}>{drawResult.winner_name}</div>
              <div className="sub mt4">Prize: {drawResult.pool.toFixed(2)} USD · Had {drawResult.winner_pct}% chance</div>
            </div>
          )}

          <button className="btn" disabled={!canOpen || busy.new}
            onClick={() => roundAction('new', api.admin.newRound, r => `Round #${r.round_id} opened!`)}>
            {busy.new ? 'Opening…' : '🆕 Open New Round'}
          </button>
          <button className="btn btn-ghost" disabled={!canClose || busy.close}
            onClick={() => roundAction('close', api.admin.closeRound, r => `Round #${r.round_id} closed.`)}>
            {busy.close ? 'Closing…' : '🔒 Close Round'}
          </button>
          <button className="btn" disabled={!canDraw || busy.draw}
            style={{ background: canDraw ? '#f57f17' : undefined, color: canDraw ? '#fff' : undefined }}
            onClick={confirmDraw}>
            {busy.draw ? 'Drawing…' : '🎲 Draw Winner'}
          </button>
        </>
      )}

      {/* Deposits tab */}
      {tab === 'deposits' && (
        !deposits ? (
          <div style={{ textAlign: 'center', paddingTop: 40 }}><div className="spinner" style={{ margin: '0 auto' }} /></div>
        ) : deposits.length === 0 ? (
          <div className="empty-state"><div className="icon">✅</div><p>No pending deposits</p></div>
        ) : deposits.map(d => (
          <div key={d.id} className="card">
            <div className="row">
              <div>
                <div style={{ fontWeight: 600 }}>{d.full_name}</div>
                {d.username && <div className="hint">@{d.username}</div>}
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontWeight: 700, fontSize: 20 }}>{d.amount.toFixed(2)}</div>
                <div className="hint" style={{ fontSize: 11 }}>{d.created_at.slice(0, 10)}</div>
              </div>
            </div>
            <div className="row mt8" style={{ gap: 8 }}>
              <button className="btn btn-sm" style={{ flex: 1 }}
                disabled={busy[`d${d.id}`]} onClick={() => resolveDeposit(d.id, 'approve')}>
                ✅ Approve
              </button>
              <button className="btn btn-sm btn-danger" style={{ flex: 1 }}
                disabled={busy[`d${d.id}`]} onClick={() => resolveDeposit(d.id, 'reject')}>
                ❌ Reject
              </button>
            </div>
          </div>
        ))
      )}

      {/* Members tab */}
      {tab === 'members' && (
        !members ? (
          <div style={{ textAlign: 'center', paddingTop: 40 }}><div className="spinner" style={{ margin: '0 auto' }} /></div>
        ) : (
          <div className="card">
            {members.map(m => (
              <div key={m.telegram_id} className="list-row">
                <div>
                  <div style={{ fontWeight: 500 }}>{m.full_name}{m.is_trustee ? ' 👑' : ''}</div>
                  {m.username && <div className="hint" style={{ fontSize: 12 }}>@{m.username}</div>}
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 600 }}>{m.credit.toFixed(2)}</div>
                  <div className="hint" style={{ fontSize: 11 }}>USD</div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {toast && <Toast msg={toast.msg} error={toast.error} />}
    </div>
  )
}
