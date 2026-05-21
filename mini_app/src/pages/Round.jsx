import { useState, useEffect } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

// ── Date helpers ──────────────────────────────────────────────────────────────
function fmtDate(s) {
  if (!s) return ''
  const [y, m, d] = s.split('-').map(Number)
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  return `${MON[m - 1]} ${d}, ${y}`
}

function drawLabel(s) {
  if (!s) return null
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const draw  = new Date(s + 'T00:00:00')
  const diff  = Math.round((draw - today) / 86400000)
  if (diff === 0)  return 'Draw is today'
  if (diff === 1)  return 'Draw is tomorrow'
  if (diff > 1)   return `Draw in ${diff} days`
  return `Drawn ${-diff} day${-diff !== 1 ? 's' : ''} ago`
}

// ── Status badge ─────────────────────────────────────────────────────────────
const STATUS_CFG = {
  live:    { cls: 'bg-green',  label: 'Live'         },
  closing: { cls: 'bg-yellow', label: 'Closing Soon' },
  done:    { cls: 'bg-red',    label: 'Done'         },
}

function StatusBadge({ ds }) {
  const { cls, label } = STATUS_CFG[ds] ?? { cls: 'bg-gray', label: ds }
  return <span className={`badge ${cls}`}>{label}</span>
}

// ── Done: results view ────────────────────────────────────────────────────────
function DoneView({ round, currency }) {
  const { pool, winner_name, participants, my_won, my_stake, my_pct, drawn_at } = round
  return (
    <>
      {/* Winner card */}
      <div className="card" style={{ border: '2px solid #f44336', textAlign: 'center', padding: '20px 16px' }}>
        <div style={{ fontSize: 40, marginBottom: 8 }}>🏆</div>
        <div style={{ fontWeight: 700, fontSize: 20 }}>{winner_name}</div>
        <div style={{ fontWeight: 700, fontSize: 28, color: '#27ae60', margin: '6px 0' }}>
          {pool.toFixed(2)} {currency}
        </div>
        <div className="hint">Prize pool won</div>
        {drawn_at && <div className="hint" style={{ fontSize: 11, marginTop: 4 }}>
          Drawn {drawn_at.slice(0, 10)}
        </div>}
      </div>

      {/* My result */}
      {my_stake != null && (
        <div className="card" style={{
          background: my_won ? '#e8f5e9' : '#fce4ec',
          border: `1.5px solid ${my_won ? '#a5d6a7' : '#ef9a9a'}`,
        }}>
          <div style={{ fontWeight: 600, fontSize: 16 }}>
            {my_won ? '🏆 You won!' : "😔 You didn't win this time"}
          </div>
          <div className="hint mt4">
            Your stake: {my_stake.toFixed(2)} {currency} · {my_pct}% chance
          </div>
          {my_won && (
            <div style={{ fontWeight: 700, fontSize: 20, color: '#27ae60', marginTop: 6 }}>
              +{pool.toFixed(2)} {currency} credited
            </div>
          )}
        </div>
      )}

      {/* All results */}
      <div className="section-label">Results</div>
      <div className="card">
        {participants.map(p => (
          <div key={p.user_id} className="list-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 20 }}>{p.won ? '✅' : '❌'}</span>
              <div>
                <div style={{ fontWeight: 500 }}>{p.full_name}</div>
                <div className="hint" style={{ fontSize: 12 }}>
                  {p.amount.toFixed(2)} {currency} · {p.pct}% chance
                </div>
              </div>
            </div>
            {p.won
              ? <div style={{ fontWeight: 700, color: '#27ae60', fontSize: 15 }}>
                  +{pool.toFixed(2)}
                </div>
              : <div className="hint">—</div>
            }
          </div>
        ))}
      </div>
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function Round({ user, onUserUpdate }) {
  const currency = 'CAD'
  const [data,   setData]   = useState(undefined)
  const [show,   setShow]   = useState(false)
  const [amount, setAmount] = useState('')
  const [busy,   setBusy]   = useState(false)
  const [toast,  setToast]  = useState(null)

  function showToast(msg, error = false) {
    setToast({ msg, error }); setTimeout(() => setToast(null), 3500)
  }

  async function load() {
    try { const d = await api.round(); setData(d.round) }
    catch { setData(null) }
  }
  useEffect(() => { load() }, [])

  async function submit(e) {
    e.preventDefault()
    const n = parseFloat(amount)
    if (!n || n <= 0) return
    setBusy(true)
    try {
      const res = await api.participate(n)
      showToast(`Staked ${n.toFixed(2)} ${currency}! Your chance: ${res.my_pct}%`)
      setAmount(''); setShow(false)
      await load()
      api.me().then(onUserUpdate).catch(() => {})
    } catch (err) {
      showToast(err.message, true)
    } finally { setBusy(false) }
  }

  // Loading
  if (data === undefined) return (
    <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  // No round ever
  if (!data) return (
    <div className="page">
      <div className="empty-state">
        <div className="icon">🎰</div>
        <p>No active round</p>
        <p className="hint">The trustee will open one soon!</p>
      </div>
    </div>
  )

  const { id, display_status: ds, pool, draw_date, participants, my_stake, my_pct } = data
  const canParticipate = ds === 'live'

  return (
    <div className="page">
      {/* Header card */}
      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <div className="card-label" style={{ marginBottom: 0 }}>Round #{id}</div>
          <StatusBadge ds={ds} />
        </div>
        <div className="big-num">{pool.toFixed(2)}</div>
        <div className="sub">
          {currency} pool · {participants.length} participant{participants.length !== 1 ? 's' : ''}
        </div>
        {draw_date && (
          <div className="hint mt8" style={{ fontSize: 13 }}>
            📅 {drawLabel(draw_date)} ({fmtDate(draw_date)})
          </div>
        )}
      </div>

      {/* Done state */}
      {ds === 'done' && <DoneView round={data} currency={currency} />}

      {/* Live / Closing state */}
      {ds !== 'done' && (
        <>
          {/* My stake */}
          {my_stake != null && (
            <div className="card">
              <div className="card-label">Your Stake</div>
              <div className="row">
                <span style={{ fontWeight: 600, fontSize: 18 }}>{my_stake.toFixed(2)} {currency}</span>
                <span className="badge bg-blue">{my_pct}% chance</span>
              </div>
            </div>
          )}

          {/* Participate / closing notice */}
          {canParticipate
            ? <button className="btn" onClick={() => setShow(true)}>
                {my_stake != null ? 'Add More Stake' : '🎟 Participate'}
              </button>
            : <div className="card" style={{ background: '#fff8e1', border: '1.5px solid #ffe082', textAlign: 'center' }}>
                <div style={{ fontWeight: 600, color: '#e65100' }}>⏳ Participation Closed</div>
                <div className="hint mt4">The draw is imminent — no more entries.</div>
              </div>
          }

          {/* Participants */}
          {participants.length > 0 && (
            <>
              <div className="section-label">Participants</div>
              <div className="card">
                {participants.map(p => (
                  <div key={p.user_id} style={{ marginBottom: 14 }}>
                    <div className="row">
                      <span style={{ fontWeight: 500 }}>{p.full_name}</span>
                      <span className="hint">{p.pct}%</span>
                    </div>
                    <div className="bar">
                      <div className="bar-fill" style={{ width: `${p.pct}%` }} />
                    </div>
                    <div className="hint" style={{ fontSize: 11 }}>{p.amount.toFixed(2)} {currency}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      {/* Participate modal */}
      {show && (
        <div className="overlay" onClick={() => setShow(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-title">{my_stake != null ? 'Add Stake' : 'Participate'} — Round #{id}</div>
            {draw_date && (
              <div className="hint" style={{ marginBottom: 12 }}>
                📅 {drawLabel(draw_date)} ({fmtDate(draw_date)})
              </div>
            )}
            <p className="hint" style={{ marginBottom: 12 }}>
              Balance: <strong>{user.credit.toFixed(2)} {currency}</strong>
            </p>
            <form onSubmit={submit}>
              <input className="inp" type="number" min="0.01" max={user.credit} step="any"
                placeholder={`Amount (${currency})`} value={amount}
                onChange={e => setAmount(e.target.value)} autoFocus />
              <button className="btn mb0" type="submit" disabled={busy || !amount}>
                {busy ? 'Processing…' : 'Confirm Stake'}
              </button>
            </form>
          </div>
        </div>
      )}

      {toast && <Toast msg={toast.msg} error={toast.error} />}
    </div>
  )
}
