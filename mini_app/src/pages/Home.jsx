import { useState, useEffect } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { api } from '../api.js'
import Toast from '../components/Toast.jsx'

const STRIPE_APPEARANCE = {
  theme: 'night',
  variables: {
    colorPrimary: '#5288c1',
    colorBackground: '#17212b',
    colorText: '#f5f5f5',
    colorDanger: '#e74c3c',
    borderRadius: '10px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  },
}

const INPUT_STYLE = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 10,
  border: '1.5px solid var(--tg-theme-hint-color, #555)',
  background: 'var(--tg-theme-secondary-bg-color, #232e3c)',
  color: 'var(--tg-theme-text-color, #f5f5f5)',
  fontSize: 15,
  boxSizing: 'border-box',
  outline: 'none',
}

function PaymentForm({ onSuccess, onError }) {
  const stripe   = useStripe()
  const elements = useElements()
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true)
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.origin + '/payment-success' },
      redirect: 'if_required',
    })
    setBusy(false)
    if (error) onError(error.message)
    else onSuccess()
  }

  return (
    <form onSubmit={submit}>
      <PaymentElement options={{ layout: 'tabs' }} />
      <button
        type="submit"
        disabled={busy || !stripe}
        className="btn"
        style={{ width: '100%', marginTop: 16 }}
      >
        {busy ? 'Processing\u2026' : 'Pay Now'}
      </button>
    </form>
  )
}

const SHEET_STYLE = {
  background: 'var(--tg-theme-bg-color, #17212b)',
  borderRadius: '18px 18px 0 0',
  padding: '20px 16px 40px',
  width: '100%',
  boxSizing: 'border-box',
  maxHeight: '90vh',
  overflowY: 'auto',
}

const OVERLAY_STYLE = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex', alignItems: 'flex-end',
  zIndex: 200,
}

function Sheet({ title, onClose, children }) {
  return (
    <div style={OVERLAY_STYLE} onClick={onClose}>
      <div style={SHEET_STYLE} onClick={e => e.stopPropagation()}>
        <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 20 }}>{title}</div>
        {children}
        <button
          className="btn"
          style={{ width: '100%', marginTop: 10, background: 'transparent',
                   color: 'var(--tg-theme-hint-color, #888)', border: 'none' }}
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function Home({ user, onUserUpdate }) {
  const [amount,       setAmount]       = useState('')
  const [stripePromise,setStripePromise]= useState(null)
  const [sheet,        setSheet]        = useState(null)   // { clientSecret, label }
  const [sub,          setSub]          = useState(null)
  const [changingAmt,  setChangingAmt]  = useState(false)
  const [newAmt,       setNewAmt]       = useState('')
  const [toast,        setToast]        = useState(null)

  const currency = user.currency || 'CAD'
  const hasSub   = sub && !sub.cancel_at_period_end

  useEffect(() => {
    if (!user.stripe_enabled) return
    api.stripe.config().then(cfg => setStripePromise(loadStripe(cfg.publishable_key)))
    api.stripe.subscription().then(r => setSub(r.subscription))
  }, [user.stripe_enabled])

  function toast_(msg, error = false) { setToast({ msg, error }) }

  async function openSheet(type) {
    const amt = parseFloat(amount)
    if (!amt || amt <= 0) { toast_('Enter a valid amount', true); return }
    try {
      if (type === 'once') {
        const r = await api.stripe.createPaymentIntent(amt)
        setSheet({ clientSecret: r.client_secret, label: `Pay ${amt.toFixed(2)} ${currency}` })
      } else {
        const r = await api.stripe.createSubscription(amt)
        setSheet({ clientSecret: r.client_secret, label: `Subscribe ${amt.toFixed(2)} ${currency}/month` })
      }
    } catch (e) { toast_(e.message || 'Error', true) }
  }

  function onPaySuccess() {
    setSheet(null)
    setAmount('')
    toast_('Payment received! Balance updates in a moment.')
    setTimeout(() => {
      api.me().then(onUserUpdate)
      api.stripe.subscription().then(r => setSub(r.subscription))
    }, 3000)
  }

  async function cancelSub() {
    try {
      await api.stripe.cancelSub()
      setSub(s => s ? { ...s, cancel_at_period_end: true } : s)
      toast_('Subscription will cancel at end of period.')
    } catch (e) { toast_(e.message || 'Error', true) }
  }

  async function updateSub() {
    const amt = parseFloat(newAmt)
    if (!amt || amt <= 0) return
    try {
      await api.stripe.updateSub(amt)
      setSub(s => s ? { ...s, amount: amt } : s)
      setChangingAmt(false)
      toast_('Subscription amount updated.')
    } catch (e) { toast_(e.message || 'Error', true) }
  }

  return (
    <div className="page">
      {toast && <Toast msg={toast.msg} error={toast.error} onClose={() => setToast(null)} />}

      <div className="card" onClick={() => api.me().then(onUserUpdate)} style={{ cursor: 'pointer' }}>
        <div className="hint">Balance</div>
        <div style={{ fontSize: 32, fontWeight: 700 }}>{(user.credit ?? 0).toFixed(2)} {currency}</div>
        <div className="hint mt4">Tap to refresh</div>
      </div>

      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 600 }}>
            {user.full_name || user.username || `User ${user.telegram_id}`}
          </span>
          {user.is_trustee && <span className="badge bg-blue">Admin</span>}
        </div>
        <div className="hint mt4">ID: {user.telegram_id}</div>
      </div>

      {hasSub && (
        <div className="card">
          <div style={{ fontWeight: 600 }}>Monthly Subscription</div>
          <div className="hint mt4">{sub.amount?.toFixed(2)} {currency}/month</div>
          {sub.next_billing && <div className="hint mt4">Next billing: {sub.next_billing}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="btn" style={{ flex: 1 }}
              onClick={() => { setNewAmt(String(sub.amount || '')); setChangingAmt(true) }}>
              Change Amount
            </button>
            <button className="btn" style={{ flex: 1, background: '#c0392b' }} onClick={cancelSub}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {sub?.cancel_at_period_end && (
        <div className="card" style={{ borderColor: '#e67e22' }}>
          <div style={{ fontWeight: 600 }}>Subscription Canceling</div>
          {sub.next_billing && <div className="hint mt4">Active until {sub.next_billing}</div>}
        </div>
      )}

      {user.stripe_enabled && (
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 10 }}>Deposit Funds</div>
          <input
            type="number" min="1" step="0.01"
            placeholder={`Amount (${currency})`}
            value={amount}
            onChange={e => setAmount(e.target.value)}
            style={INPUT_STYLE}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button className="btn" style={{ flex: 1 }} onClick={() => openSheet('once')}>
              Pay Once
            </button>
            <button className="btn" style={{ flex: 1 }} disabled={!!hasSub}
              onClick={() => openSheet('sub')}>
              {hasSub ? 'Subscribed' : 'Monthly'}
            </button>
          </div>
        </div>
      )}

      {sheet && stripePromise && (
        <Sheet title={sheet.label} onClose={() => setSheet(null)}>
          <Elements
            stripe={stripePromise}
            options={{ clientSecret: sheet.clientSecret, appearance: STRIPE_APPEARANCE }}
          >
            <PaymentForm onSuccess={onPaySuccess} onError={msg => toast_(msg, true)} />
          </Elements>
        </Sheet>
      )}

      {changingAmt && (
        <Sheet title="Change Monthly Amount" onClose={() => setChangingAmt(false)}>
          <input
            type="number" min="1" step="0.01"
            placeholder={`New amount (${currency})`}
            value={newAmt}
            onChange={e => setNewAmt(e.target.value)}
            style={INPUT_STYLE}
          />
          <button className="btn" style={{ width: '100%', marginTop: 10 }} onClick={updateSub}>
            Update
          </button>
        </Sheet>
      )}
    </div>
  )
}
