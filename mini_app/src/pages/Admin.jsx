import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

const STATUS_CFG = {
  live:    { cls: 'bg-green',  label: 'Live'         },
  closing: { cls: 'bg-yellow', label: 'Closing Soon' },
  done:    { cls: 'bg-red',    label: 'Done'         },
  open:    { cls: 'bg-green',  label: 'Open'         },
  closed:  { cls: 'bg-yellow', label: 'Closed'       },
  drawn:   { cls: 'bg-blue',   label: 'Drawn'        },
}

function StatusBadge({ s }) {
  const { cls, label } = STATUS_CFG[s] ?? { cls: 'bg-gray', label: s }
  return <span className={`badge ${cls}`}>{label}</span>
}

function fmtDate(s) {
  if (!s) return ''
  const [y, m, d] = s.split('-').map(Number)
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${MON[m - 1]} ${d}, ${y}`
}

// Today's date in YYYY-MM-DD for the date input min attribute
const TODAY = new Date().toISOString().slice(0, 10)

export default function Admin() {
  const currency = 'CAD'
  const [tab,        setTab]        = useState('round')
  const [round,      setRound]      = useState(undefined)
  const [deposits,   setDeposits]   = useState(null)
  const [members,    setMembers]    = useState(null)
  const [busy,       setBusy]       = useState({})
  const [toast,      setToast]      = useState(null)
  const [drawResult, setDrawResult] = useState(null)
  const [showNew,    setShowNew]    = useState(false)
  const [newDate,    setNewDate]    = useState('')

  function showToast(msg, error = false) {
    setToast({ msg, error }); setTimeout(() => setToast(null), 4000)
  }

  const loadRound    = useCallback(() =>
    api.admin.round().then(d => setRound(d.round)).catch(() => setRound(null)), [])
  const loadDeposits = useCallback(() =>
    api.admin.deposits().then(d => setDeposits(d.deposits)).catch(() => setDeposits([])), [])
  const loadMembers  = useCallback(() =>
    api.admin.members().then(d => setMembers(d.members)).catch(() => setMembers([])), [])

  useEffect(() => { loadRound(); loadDeposits(); loadMembers() }, [])

  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  async function openRound() {
    setB('new', true)
    try {
      const res = await api.admin.newRound(newDate || undefined)
      showToast(`Round #${res.round_id} opened!${newDate ? ` Draw: ${fmtDate(newDate)}` : ''}`)
      await loadRound()
      setShowNew(false); setNewDate('')
    } catch (err) { showToast(err.message, true) }
    finally { setB('new', false) }
  }

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
    const run = () => roundAction('draw', api.admin.draw,
      r => `Winner: ${r.winner_name} — ${r.pool.toFixed(2)} ${currency}`)
    const tg = window.Telegram?.WebApp
    if (tg?.showConfirm) tg.showConfirm('Draw a winner now? This cannot be undone.', ok => { if (ok) run() })
    else if (window.confirm('Draw a winner now? This cannot be undone.')) run()
  }

  const ds       = round?.display_status
  const st       = round?.status
  const canOpen  = !round || ds === 'done'
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

      {/* ── Round tab ── */}
      {tab === 'round' && (
        <>
          {round && (
            <div className="card">
              <div className="row" style={{ marginBottom: 8 }}>
                <div className="card-label" style={{ marginBottom: 0 }}>Round #{round.id}</div>
                <StatusBadge s={ds || st} />
              </div>
              <div className="big-num">{round.pool.toFixed(2)}</div>
              <div className="sub mt4">
                {currency} · {round.participants.length} participant{round.participants.length !== 1 ? 's' : ''}
              </div>
              {round.draw_date && (
                <div className="hint mt8" style={{ fontSize: 13 }}>
                  📅 Draw date: {fmtDate(round.draw_date)}
                </div>
              )}
              {round.participants.length > 0 && (
                <div style={{ marginTop: 14 }}>
                  {round.participants.map(p => (
                    <div key={p.user_id} style={{ marginBottom: 10 }}>
                      <div className="row">
                        <span style={{ fontSize: 14 }}>
                          {p.won ? '🏆 ' : ''}{p.full_name}
                        </span>
                        <span className="hint" style={{ fontSize: 13 }}>
                          {p.pct}% · {p.amount.toFixed(2)}
                        </span>
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
              <div className="sub mt4">
                Prize: {drawResult.pool.toFixed(2)} {currency} · Had {drawResult.winner_pct}% chance
              </div>
            </div>
          )}

          <button className="btn" disabled={!canOpen || busy.new}
            onClick={() => setShowNew(true)}>
            🆕 Open New Round
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

      {/* ── Deposits tab ── */}
      {tab === 'deposits' && (
        !deposits ? (
          <div style={{ textAlign: 'center', paddingTop: 40 }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
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

      {/* ── Members tab ── */}
      {tab === 'members' && (
        !members ? (
          <div style={{ textAlign: 'center', paddingTop: 40 }}>
            <div className="spinner" style={{ margin: '0 auto' }} />
          </div>
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
                  <div className="hint" style={{ fontSize: 11 }}>{currency}</div>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* ── New round modal ── */}
      {showNew && (
        <div className="overlay" onClick={() => setShowNew(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-title">Open New Round</div>
            <p className="hint" style={{ marginBottom: 12 }}>
              Set a draw date so participants know when the lottery closes.
            </p>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600,
                            color: 'var(--hint)', marginBottom: 6 }}>
              Draw Date
            </label>
            <input className="inp" type="date" min={TODAY} value={newDate}
              onChange={e => setNewDate(e.target.value)} />
            <button className="btn mb0" disabled={busy.new} onClick={openRound}>
              {busy.new ? 'Opening…' : '🆕 Open Round'}
            </button>
          </div>
        </div>
      )}

      {toast && <Toast msg={toast.msg} error={toast.error} />}
    </div>
  )
}
