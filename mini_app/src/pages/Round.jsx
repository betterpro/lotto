import { useState, useEffect } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

export default function Round({ user, onUserUpdate }) {
  const [data,   setData]   = useState(undefined)
  const [show,   setShow]   = useState(false)
  const [amount, setAmount] = useState('')
  const [busy,   setBusy]   = useState(false)
  const [toast,  setToast]  = useState(null)

  function showToast(msg, error = false) {
    setToast({ msg, error })
    setTimeout(() => setToast(null), 3500)
  }

  async function load() { const d = await api.round(); setData(d.round) }
  useEffect(() => { load() }, [])

  async function submit(e) {
    e.preventDefault()
    const n = parseFloat(amount)
    if (!n || n <= 0) return
    setBusy(true)
    try {
      const res = await api.participate(n)
      showToast(`Staked ${n.toFixed(2)} USD! Your chance: ${res.my_pct}%`)
      setAmount(''); setShow(false)
      await load()
      api.me().then(onUserUpdate).catch(() => {})
    } catch (err) {
      showToast(err.message, true)
    } finally { setBusy(false) }
  }

  if (data === undefined) return (
    <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  if (!data) return (
    <div className="page">
      <div className="empty-state">
        <div className="icon">🎰</div>
        <p>No active round</p>
        <p className="hint">The trustee will open one soon!</p>
      </div>
    </div>
  )

  const { id, pool, participants, my_stake, my_pct } = data
  return (
    <div className="page">
      <div className="card">
        <div className="row">
          <div className="card-label" style={{ marginBottom: 0 }}>Round #{id}</div>
          <span className="badge bg-green">Open</span>
        </div>
        <div className="big-num mt8">{pool.toFixed(2)}</div>
        <div className="sub">USD · {participants.length} participant{participants.length !== 1 ? 's' : ''}</div>
      </div>

      {my_stake != null && (
        <div className="card">
          <div className="card-label">Your Stake</div>
          <div className="row">
            <span style={{ fontWeight: 600, fontSize: 18 }}>{my_stake.toFixed(2)} USD</span>
            <span className="badge bg-blue">{my_pct}% chance</span>
          </div>
        </div>
      )}

      <button className="btn" onClick={() => setShow(true)}>
        {my_stake != null ? 'Add More Stake' : '🎟 Participate'}
      </button>

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
                <div className="hint" style={{ fontSize: 11 }}>{p.amount.toFixed(2)} USD</div>
              </div>
            ))}
          </div>
        </>
      )}

      {show && (
        <div className="overlay" onClick={() => setShow(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-title">{my_stake != null ? 'Add Stake' : 'Participate'} — Round #{id}</div>
            <p className="hint" style={{ marginBottom: 12 }}>
              Balance: <strong>{user.credit.toFixed(2)} USD</strong>
            </p>
            <form onSubmit={submit}>
              <input className="inp" type="number" min="0.01" max={user.credit} step="any"
                placeholder="Amount (USD)" value={amount}
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
