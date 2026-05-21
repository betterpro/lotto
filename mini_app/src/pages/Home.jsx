import { useState, useEffect } from 'react'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s + 'T12:00:00')
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function Home({ user, onUserUpdate }) {
  const currency = 'CAD'

  // Stripe subscription state
  const [sub,        setSub]        = useState(undefined)  // undefined = loading
  const [subLoaded,  setSubLoaded]  = useState(false)

  // Payment form state
  const [amount,     setAmount]     = useState('')
  const [newAmt,     setNewAmt]     = useState('')
  const [showUpdate, setShowUpdate] = useState(false)

  // Busy flags: { one_time, subscription, update, cancel, refresh }
  const [busy,  setBusy]  = useState({})
  const [toast, setToast] = useState(null)

  function showToast(msg, error = false) {
    setToast({ msg, error }); setTimeout(() => setToast(null), 4000)
  }
  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  useEffect(() => {
    if (!user.stripe_enabled) { setSubLoaded(true); setSub(null); return }
    api.stripe.subscription()
      .then(d => { setSub(d.subscription); setSubLoaded(true) })
      .catch(() => { setSub(null); setSubLoaded(true) })
  }, [user.stripe_enabled])

  async function refreshBalance() {
    setB('refresh', true)
    try {
      const updated = await api.me()
      onUserUpdate(updated)
      showToast('Balance refreshed!')
    } catch { showToast('Could not refresh', true) }
    finally { setB('refresh', false) }
  }

  function openStripe(type) {
    const n = parseFloat(amount)
    if (!n || n < 1) { showToast('Enter at least 1 CAD', true); return }
    setB(type, true)
    api.stripe.checkout(n, type)
      .then(({ checkout_url }) => {
        const tg = window.Telegram?.WebApp
        if (tg?.openLink) tg.openLink(checkout_url)
        else window.open(checkout_url, '_blank')
      })
      .catch(e => showToast(e.message, true))
      .finally(() => setB(type, false))
  }

  async function updateSub() {
    const n = parseFloat(newAmt)
    if (!n || n < 1) { showToast('Enter at least 1 CAD', true); return }
    setB('update', true)
    try {
      await api.stripe.updateSub(n)
      setSub(s => ({ ...s, amount: n }))
      showToast(`Subscription updated to ${n.toFixed(2)} ${currency}/month`)
      setShowUpdate(false); setNewAmt('')
    } catch (e) { showToast(e.message, true) }
    finally { setB('update', false) }
  }

  function cancelSub() {
    const run = async () => {
      setB('cancel', true)
      try {
        await api.stripe.cancelSub()
        setSub(s => ({ ...s, status: 'cancelling' }))
        showToast('Subscription will end at the current billing period.')
      } catch (e) { showToast(e.message, true) }
      finally { setB('cancel', false) }
    }
    const tg = window.Telegram?.WebApp
    if (tg?.showConfirm) tg.showConfirm('Cancel your monthly subscription?', ok => { if (ok) run() })
    else if (window.confirm('Cancel your monthly subscription?')) run()
  }

  const hasActiveSub = sub && sub.status === 'active'
  const isCancelling = sub && sub.status === 'cancelling'

  return (
    <div className="page">

      {/* ── Balance ── */}
      <div className="card" style={{ cursor: 'pointer' }} onClick={refreshBalance}>
        <div className="card-label">Balance {busy.refresh && '\u2026'}</div>
        <div className="big-num">{user.credit.toFixed(2)}</div>
        <div className="sub">{currency} available \u00b7 tap to refresh</div>
      </div>

      {/* ── Account ── */}
      <div className="card">
        <div className="card-label">Account</div>
        <div style={{ fontWeight: 600 }}>{user.full_name}</div>
        {user.username && <div className="hint mt4">@{user.username}</div>}
        {user.is_trustee && <div className="mt8"><span className="badge bg-blue">Trustee \ud83d\udc51</span></div>}
      </div>

      {/* ── Active subscription card ── */}
      {subLoaded && (hasActiveSub || isCancelling) && (
        <div className="card" style={{ border: '1.5px solid var(--btn)' }}>
          <div className="row" style={{ marginBottom: 8 }}>
            <div className="card-label" style={{ marginBottom: 0 }}>Monthly Subscription</div>
            <span className={`badge ${isCancelling ? 'bg-yellow' : 'bg-green'}`}>
              {isCancelling ? 'Cancelling' : 'Active'}
            </span>
          </div>
          <div style={{ fontWeight: 700, fontSize: 22 }}>
            {sub.amount.toFixed(2)} {currency}<span style={{ fontWeight: 400, fontSize: 14 }}>/month</span>
          </div>
          {sub.next_billing && (
            <div className="hint mt4">
              {isCancelling ? 'Active until' : 'Next charge'}: {fmtDate(sub.next_billing)}
            </div>
          )}
          {!isCancelling && (
            <div className="row mt8" style={{ gap: 8 }}>
              <button className="btn btn-sm btn-ghost" style={{ flex: 1 }}
                onClick={() => { setShowUpdate(true); setNewAmt(sub.amount.toFixed(2)) }}>
                \u270f\ufe0f Change Amount
              </button>
              <button className="btn btn-sm btn-danger" style={{ flex: 1 }}
                disabled={busy.cancel} onClick={cancelSub}>
                {busy.cancel ? '\u2026' : '\u2715 Cancel'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Stripe payment section ── */}
      {user.stripe_enabled && (
        <>
          <div className="section-label">Add Funds</div>

          <input className="inp" type="number" min="1" step="any"
            placeholder={`Amount (${currency})`} value={amount}
            onChange={e => setAmount(e.target.value)} />

          <button className="btn" disabled={busy.one_time || !amount}
            onClick={() => openStripe('one_time')}>
            {busy.one_time ? 'Redirecting\u2026' : '\ud83d\udcb3 Pay Once with Stripe'}
          </button>

          <button className="btn btn-ghost" disabled={busy.subscription || !amount || hasActiveSub || isCancelling}
            onClick={() => openStripe('subscription')}
            title={hasActiveSub ? 'You already have an active subscription' : ''}>
            {busy.subscription ? 'Redirecting\u2026'
             : hasActiveSub    ? '\ud83d\udd04 Already Subscribed'
             : '\ud83d\udd04 Subscribe Monthly'}
          </button>

          <div className="hint" style={{ textAlign: 'center', fontSize: 12 }}>
            Powered by Stripe \u00b7 payments are secure & encrypted
          </div>
        </>
      )}

      {/* ── Change amount sheet ── */}
      {showUpdate && (
        <div className="overlay" onClick={() => setShowUpdate(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="sheet-title">Change Monthly Amount</div>
            <p className="hint" style={{ marginBottom: 12 }}>
              Current: <strong>{sub?.amount?.toFixed(2)} {currency}/month</strong><br />
              Changes take effect on your next billing cycle.
            </p>
            <input className="inp" type="number" min="1" step="any"
              placeholder={`New amount (${currency})`} value={newAmt}
              onChange={e => setNewAmt(e.target.value)} autoFocus />
            <button className="btn mb0" disabled={busy.update || !newAmt} onClick={updateSub}>
              {busy.update ? 'Updating\u2026' : 'Update Subscription'}
            </button>
          </div>
        </div>
      )}

      {toast && <Toast msg={toast.msg} error={toast.error} />}
    </div>
  )
}
