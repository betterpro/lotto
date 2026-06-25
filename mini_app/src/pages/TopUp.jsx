import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'

const STRIPE_APPEARANCE = {
  theme: 'night',
  variables: {
    colorPrimary: '#2EA6FF', colorBackground: '#1f2c3a',
    colorText: '#ffffff', colorDanger: '#F25C5C', borderRadius: '10px',
  },
}

const CARD_AMOUNTS = [25, 50, 100, 250]

function suggestTopUpAmount(shortfall, presets) {
  const list = presets?.length ? presets : CARD_AMOUNTS
  const needed = Math.max(list[0], Math.ceil(shortfall))
  return list.find(p => p >= needed) ?? list[list.length - 1]
}

// ─── Stripe payment form ────────────────────────────────────────────────────
function PaymentForm({ onSuccess, onError }) {
  const stripe = useStripe(), elements = useElements()
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true)
    const { error } = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.origin },
      redirect: 'if_required',
    })
    setBusy(false)
    if (error) onError(error.message)
    else onSuccess()
  }
  return (
    <form onSubmit={submit}>
      <PaymentElement options={{ layout: 'tabs' }} />
      <button type="submit" disabled={busy || !stripe}
        className="btn btn-primary btn-block" style={{ marginTop: 16 }}>
        {busy ? 'Processing…' : 'Pay Now'}
      </button>
    </form>
  )
}

// Screen header with a back affordance, mirroring the in-app tab chrome.
function ScreenHead({ title, onBack }) {
  return (
    <div className="screen-head">
      <button className="screen-back" onClick={onBack} aria-label="Back">←</button>
      <span className="screen-title">{title}</span>
    </div>
  )
}

// ─── Top-up screen ───────────────────────────────────────────────────────────
// A dedicated route rather than a modal: nesting a fixed overlay inside the
// app's -webkit-overflow-scrolling scroll container traps it on iOS (Telegram),
// hiding the action button. A real screen lays out in normal flow, so the CTA is
// always reachable.
export default function TopUp({ user, onUserUpdate }) {
  const navigate = useNavigate()
  const showToast = useToast()
  const goHome = () => navigate('/', { replace: true })

  const [tab, setTab]           = useState('once')
  const [amount, setAmount]     = useState(50)
  const [customInput, setCustomInput] = useState('')
  const [method, setMethod]     = useState('card')   // 'card' | 'etransfer'
  const [step, setStep]         = useState('select') // 'select' | 'card' | 'sent'
  const [stripePromise, setSP]  = useState(null)
  const [clientSecret, setCS]   = useState(null)
  const [etxInfo, setEtxInfo]   = useState(null)     // { admin_email, amount }
  const [payOpts, setPayOpts]   = useState(null)
  const [senderEmail, setSenderEmail] = useState(user?.email || '')

  useEffect(() => {
    api.payment.options().then(opts => {
      setPayOpts(opts)
      const presets = opts.card_enabled ? opts.card_amounts : opts.etransfer_amounts
      setAmount(presets?.[1] ?? presets?.[0] ?? 50)
      setCustomInput('')
      if (opts.card_enabled) setMethod('card')
      else if (opts.etransfer_enabled) setMethod('etransfer')
    }).catch(() => setPayOpts({ card_enabled: true, etransfer_enabled: true, card_amounts: CARD_AMOUNTS, etransfer_amounts: CARD_AMOUNTS }))
    api.stripe.config().then(cfg => setSP(loadStripe(cfg.publishable_key))).catch(() => {})
  }, [])

  function resetMethod() { setCS(null); setStep('select') }

  function handleSuccess(amt, plan) {
    if (plan === 'once') {
      showToast(`Added $${amt} credit — open Join when you are ready`, 'success')
    } else if (plan === 'etransfer') {
      showToast('After approval, top up completes — then join the round from Home', 'info')
    } else {
      showToast(`Subscribed · $${amt}/mo`, 'success')
    }
    setTimeout(() => api.me().then(onUserUpdate).catch(() => {}), 3000)
    goHome()
  }

  const cardAmounts = payOpts?.card_amounts ?? CARD_AMOUNTS
  const etxAmounts = (payOpts?.etransfer_amounts?.length ? payOpts.etransfer_amounts : cardAmounts)
  const presets = method === 'card' ? cardAmounts : etxAmounts
  const chargeAmt = amount
  const etxMin = payOpts?.etransfer_min_amount ?? 25
  const usingCustomAmt = method === 'etransfer' && customInput !== ''

  useEffect(() => {
    if (!payOpts || !presets.length || method === 'etransfer') return
    setCustomInput('')
    setAmount(prev => (presets.includes(prev) ? prev : suggestTopUpAmount(prev, presets)))
  }, [method, payOpts])

  function selectPreset(p) {
    setAmount(p)
    setCustomInput('')
  }

  function onCustomAmountChange(raw) {
    setCustomInput(raw)
    const n = parseFloat(raw)
    if (!isNaN(n) && n > 0) setAmount(Math.round(n * 100) / 100)
  }

  function selectMethod(id) {
    setMethod(id)
    if (id === 'card') setCustomInput('')
  }

  const methodChoices = [
    payOpts?.card_enabled && { id: 'card', icon: '💳', label: 'Card' },
    payOpts?.etransfer_enabled && { id: 'etransfer', icon: '🏦', label: 'E-Transfer' },
  ].filter(Boolean)

  const etxAmountInvalid = method === 'etransfer' && (
    amount <= 0 || amount < etxMin || (usingCustomAmt && (isNaN(parseFloat(customInput)) || parseFloat(customInput) <= 0))
  )

  // Each user must register the email they'll send the Interac e-Transfer from,
  // so incoming transfers can be auto-matched. Collect it here when missing
  // rather than dead-ending on the server's "set it in Profile" error.
  const hasSenderEmail = !!user?.email
  const senderEmailValid = senderEmail.trim().includes('@') && senderEmail.trim().length >= 3
  const emailBlocksEtx = method === 'etransfer' && !hasSenderEmail && !senderEmailValid

  async function proceed() {
    if (method === 'card') {
      try {
        const r = tab === 'once'
          ? await api.stripe.createPaymentIntent(amount)
          : await api.stripe.createSubscription(amount)
        setCS(r.client_secret)
        setStep('card')
      } catch (e) { showToast(e.message, 'error') }
    } else {
      try {
        if (!hasSenderEmail) {
          if (!senderEmailValid) { showToast('Enter a valid e-transfer email', 'error'); return }
          await api.profile.updateEmail(senderEmail.trim().toLowerCase())
        }
        const r = await api.etransfer.deposit(amount)
        setEtxInfo(r)
        setStep('sent')
      } catch (e) { showToast(e.message, 'error') }
    }
  }

  function copy(text, label = 'Copied') {
    navigator.clipboard?.writeText(text)
      .then(() => showToast(label, 'success'))
      .catch(() => showToast('Could not copy', 'error'))
  }

  // ── E-transfer instructions ──
  if (step === 'sent' && etxInfo) return (
    <div className="tab-content">
      <ScreenHead title="E-Transfer Details" onBack={goHome} />
      <div className="screen-body">
        <div style={{ textAlign: 'center', fontSize: 36, marginBottom: 8 }}>🏦</div>
        <p style={{ textAlign: 'center', fontSize: 14, color: 'var(--tx-2)', marginBottom: 18 }}>
          Send <strong style={{ color: '#fff' }}>${amount.toFixed(2)} CAD</strong> via Interac e-Transfer
        </p>
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="row between" style={{ marginBottom: 4 }}>
            <span style={{ fontSize: 12, color: 'var(--tx-2)', textTransform: 'uppercase', letterSpacing: '.3px', fontWeight: 600 }}>Send to</span>
            <button onClick={() => copy(etxInfo.admin_email, 'Email copied')}
              style={{ background: 'none', border: 'none', color: 'var(--tg)', fontSize: 13, cursor: 'pointer', fontWeight: 600 }}>
              Copy
            </button>
          </div>
          <span className="mono" style={{ fontSize: 15, wordBreak: 'break-all' }}>{etxInfo.admin_email || '(not configured)'}</span>
        </div>
        <div style={{ background: 'rgba(78,208,122,.08)', border: '.5px solid rgba(78,208,122,.25)',
          borderRadius: 10, padding: '12px 14px', fontSize: 13,
          color: 'var(--money)', lineHeight: 1.6 }}>
          ✓ Your account will be credited automatically once we detect your transfer. Usually within minutes.
        </div>
      </div>

      <div className="screen-cta">
        <button className="btn btn-primary btn-block" onClick={() => handleSuccess(amount, 'etransfer')}>
          Done — I've sent it
        </button>
      </div>
    </div>
  )

  // ── Stripe card form ──
  if (step === 'card' && clientSecret && stripePromise) return (
    <div className="tab-content">
      <ScreenHead title={`Pay $${amount.toFixed(2)} by card`} onBack={resetMethod} />
      <div className="screen-body">
        <Elements stripe={stripePromise} options={{ clientSecret, appearance: STRIPE_APPEARANCE }}>
          <PaymentForm
            onSuccess={() => { setCS(null); handleSuccess(amount, tab) }}
            onError={msg => showToast(msg, 'error')}
          />
        </Elements>
        <div style={{ marginTop: 10, textAlign: 'center', fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
          🔒 Secured by Stripe · ${amount.toFixed(2)} credit
        </div>
      </div>
    </div>
  )

  // ── Main selection screen ──
  return (
    <div className="tab-content">
      <ScreenHead title="Top up credit" onBack={goHome} />
      <div className="screen-body">
        {methodChoices.length > 1 && (
          <>
            <div style={{ display: 'flex', background: 'var(--bg-3)', borderRadius: 10, padding: 4, marginBottom: 8 }}>
              {methodChoices.map(m => (
                <button key={m.id} type="button" onClick={() => selectMethod(m.id)} style={{
                  flex: 1, padding: '10px 0', borderRadius: 7, border: 0, cursor: 'pointer',
                  background: method === m.id ? 'var(--surface-2)' : 'transparent',
                  color: method === m.id ? '#fff' : 'var(--tx-2)',
                  fontWeight: 600, fontSize: 14, fontFamily: 'inherit',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                }}>
                  <span style={{ fontSize: 17 }}>{m.icon}</span>{m.label}
                </button>
              ))}
            </div>
            <p style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 16, lineHeight: 1.5 }}>
              {method === 'card'
                ? `Charged $${chargeAmt.toFixed(2)} · instant`
                : `Min $${etxMin} · 0–24 h approval`}
            </p>
          </>
        )}

        {payOpts?.card_enabled && method === 'card' && (
        <div style={{ display: 'flex', background: 'var(--bg-3)', borderRadius: 10, padding: 4, marginBottom: 16 }}>
          {[['once','One-time'],['monthly','Monthly']].map(([k,l]) => (
            <button key={k} onClick={() => { setTab(k); setCS(null) }} style={{
              flex: 1, padding: '9px 0', borderRadius: 7, border: 0, cursor: 'pointer',
              background: tab === k ? 'var(--surface-2)' : 'transparent',
              color: tab === k ? '#fff' : 'var(--tx-2)',
              fontWeight: 600, fontSize: 14, fontFamily: 'inherit',
            }}>{l}</button>
          ))}
        </div>
        )}

        {/* Amount presets */}
        <div style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.3px', fontWeight: 600 }}>Amount</div>
        {presets.length === 0 ? (
          <p style={{ fontSize: 14, color: 'var(--tx-2)', marginBottom: 16 }}>
            No payment amounts available. Ask your trustee to configure payments.
          </p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(presets.length, 4)},1fr)`, gap: 8, marginBottom: method === 'etransfer' ? 12 : 16 }}>
            {presets.map(p => (
              <button key={p} type="button" onClick={() => selectPreset(p)} style={{
                padding: '14px 0', borderRadius: 12, cursor: 'pointer',
                border: `.5px solid ${!usingCustomAmt && amount === p ? 'var(--tg)' : 'var(--hairline-2)'}`,
                background: !usingCustomAmt && amount === p ? 'rgba(46,166,255,.14)' : 'var(--bg-3)',
                color: !usingCustomAmt && amount === p ? 'var(--tg)' : '#fff',
                fontWeight: 700, fontSize: 16, fontFamily: 'var(--mono)',
              }}>${p}</button>
            ))}
          </div>
        )}

        {method === 'etransfer' && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.3px', fontWeight: 600 }}>
              Custom amount
            </div>
            <div style={{ position: 'relative' }}>
              <span className="mono" style={{
                position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)',
                color: usingCustomAmt ? 'var(--tg)' : 'var(--tx-2)', fontSize: 16, fontWeight: 700,
              }}>$</span>
              <input
                type="number"
                inputMode="decimal"
                min={etxMin}
                step="0.01"
                className="input"
                placeholder={`Min $${etxMin}`}
                value={customInput}
                onChange={e => onCustomAmountChange(e.target.value)}
                style={{
                  paddingLeft: 28,
                  fontFamily: 'var(--mono)',
                  borderColor: usingCustomAmt ? 'var(--tg)' : undefined,
                  background: usingCustomAmt ? 'rgba(46,166,255,.08)' : undefined,
                }}
              />
            </div>
          </div>
        )}

        {method === 'etransfer' && etxAmountInvalid && (
          <p style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 8, lineHeight: 1.5 }}>
            Minimum e-transfer: ${etxMin}
          </p>
        )}

        {method === 'etransfer' && !hasSenderEmail && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '.3px', fontWeight: 600 }}>
              Your e-transfer email
            </div>
            <input
              type="email"
              inputMode="email"
              autoComplete="email"
              className="input mono"
              placeholder="you@example.com"
              value={senderEmail}
              onChange={e => setSenderEmail(e.target.value)}
              style={{ borderColor: senderEmailValid ? 'var(--money)' : undefined }}
            />
            <p style={{ fontSize: 12, color: 'var(--tx-3)', marginTop: 6, lineHeight: 1.5 }}>
              The address you'll send the Interac e-Transfer from — we use it to credit your deposit automatically.
            </p>
          </div>
        )}
      </div>

      <div className="screen-cta">
        <button className="btn btn-primary btn-block" onClick={proceed}
          disabled={!presets.length || methodChoices.length === 0 || etxAmountInvalid || emailBlocksEtx}>
          {method === 'card'
            ? tab === 'once' ? `Pay $${amount.toFixed(2)} by card` : `Subscribe · $${amount.toFixed(2)}/mo`
            : `Get e-transfer details`}
        </button>
      </div>
    </div>
  )
}
