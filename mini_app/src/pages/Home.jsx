import { useState } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

export default function Home({ user, onUserUpdate }) {
  const [show,   setShow]   = useState(false)
  const [amount, setAmount] = useState('')
  const [busy,   setBusy]   = useState(false)
  const [toast,  setToast]  = useState(null)

  function showToast(msg, error = false) {
    setToast({ msg, error })
    setTimeout(() => setToast(null), 3000)
  }

  async function submit(e) {
    e.preventDefault()
    const n = parseFloat(amount)
    if (!n || n <= 0) return
    setBusy(true)
    try {
      await api.deposit(n)
      showToast(`Deposit request for ${n.toFixed(2)} USD sent — pending trustee approval.`)
      setAmount(''); setShow(false)
    } catch (err) {
      showToast(err.message, true)
    } finally { setBusy(false) }
  }

  return (
    <div className="page">
      <div className="card">
        <div className="card-label">Balance</div>
        <div className="big-num">{user.credit.toFixed(2)}</div>
        <div className="sub">USD available</div>
      </div>

      <div className="card">
        <div className="card-label">Account</div>
        <div style={{ fontWeight: 600 }}>{user.full_name}</div>
        {user.username && <div className="hint mt4">@{user.username}</div>}
        {user.is_trustee && <div className="mt8"><span className="badge bg-blue">Trustee 👑</span></div>}
      </div>

      <button className="btn" onClick={() => setShow(true)}>➕ Request Deposit</button>

      {show && (
        <div className="overlay" onClick={() => setShow(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-title">Request Deposit</div>
            <p className="hint" style={{ marginBottom: 12 }}>
              Enter the amount — the trustee will credit your balance after approval.
            </p>
            <form onSubmit={submit}>
              <input className="inp" type="number" min="1" step="any"
                placeholder="Amount (USD)" value={amount}
                onChange={e => setAmount(e.target.value)} autoFocus />
              <button className="btn mb0" type="submit" disabled={busy || !amount}>
                {busy ? 'Sending…' : 'Send Request'}
              </button>
            </form>
          </div>
        </div>
      )}

      {toast && <Toast msg={toast.msg} error={toast.error} />}
    </div>
  )
}
