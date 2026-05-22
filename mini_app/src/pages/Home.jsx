import { useState, useEffect } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { Countdown } from '../components/Countdown.jsx'
import { GiftIcon, WalletIcon, BoltIcon, PlusIcon, ShareIcon } from '../components/Icon.jsx'

const STRIPE_APPEARANCE = {
  theme: 'night',
  variables: {
    colorPrimary: '#2EA6FF', colorBackground: '#1f2c3a',
    colorText: '#ffffff', colorDanger: '#F25C5C', borderRadius: '10px',
  },
}

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

function TopUpSheet({ open, onClose, onSuccess }) {
  const [tab, setTab] = useState('once')
  const [amount, setAmount] = useState(50)
  const [stripePromise, setStripePromise] = useState(null)
  const [clientSecret, setClientSecret] = useState(null)
  const presets = [20, 50, 100, 200]

  useEffect(() => {
    if (!open) { setClientSecret(null); return }
    api.stripe.config()
      .then(cfg => setStripePromise(loadStripe(cfg.publishable_key)))
      .catch(() => {})
  }, [open])

  async function pay() {
    try {
      const r = tab === 'once'
        ? await api.stripe.createPaymentIntent(amount)
        : await api.stripe.createSubscription(amount)
      setClientSecret(r.client_secret)
    } catch (e) { alert(e.message) }
  }

  if (!open) return null
  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Top up credit</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <div style={{ display: 'flex', background: 'var(--bg-3)', borderRadius: 10, padding: 4, marginBottom: 16 }}>
            {[['once','One-time'],['monthly','Monthly']].map(([k,l]) => (
              <button key={k} onClick={() => { setTab(k); setClientSecret(null) }} style={{
                flex: 1, padding: '9px 0', borderRadius: 7, border: 0, cursor: 'pointer',
                background: tab === k ? 'var(--surface-2)' : 'transparent',
                color: tab === k ? '#fff' : 'var(--tx-2)',
                fontWeight: 600, fontSize: 13, fontFamily: 'inherit',
              }}>{l}</button>
            ))}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 16 }}>
            {presets.map(p => (
              <button key={p} onClick={() => { setAmount(p); setClientSecret(null) }} style={{
                padding: '14px 0', borderRadius: 12, cursor: 'pointer',
                border: `.5px solid ${amount === p ? 'var(--tg)' : 'var(--hairline-2)'}`,
                background: amount === p ? 'rgba(46,166,255,.14)' : 'var(--bg-3)',
                color: amount === p ? 'var(--tg)' : '#fff',
                fontWeight: 700, fontSize: 16, fontFamily: 'var(--mono)',
              }}>${p}</button>
            ))}
          </div>

          {clientSecret && stripePromise ? (
            <Elements stripe={stripePromise}
              options={{ clientSecret, appearance: STRIPE_APPEARANCE }}>
              <PaymentForm
                onSuccess={() => { setClientSecret(null); onSuccess(amount, tab); onClose() }}
                onError={msg => alert(msg)}
              />
            </Elements>
          ) : (
            <>
              {tab === 'monthly' && (
                <p style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 12, lineHeight: 1.5 }}>
                  Authorize LOTTOO to charge ${amount} CAD on the 4th of each month until cancelled.
                </p>
              )}
              <button className="btn btn-primary btn-block" onClick={pay}>
                {tab === 'once' ? `Add $${amount} credit` : `Subscribe · $${amount}/mo`}
              </button>
            </>
          )}

          <div style={{ marginTop: 10, textAlign: 'center', fontSize: 11, color: 'var(--tx-3)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
            🔒 Secured by Stripe · No card data stored on LOTTOO
          </div>
        </div>
      </div>
    </div>
  )
}

function JoinSheet({ open, onClose, round, user, onJoined }) {
  const PRICE = 5
  const [shares, setShares] = useState(1)
  const [busy, setBusy] = useState(false)
  const cost = shares * PRICE
  const after = (user?.credit ?? 0) - cost

  async function confirm() {
    setBusy(true)
    try {
      await api.participate(cost)
      onJoined(shares)
      onClose()
    } catch (e) { alert(e.message) }
    finally { setBusy(false) }
  }

  if (!open || !round) return null
  const poolAfter = (round.pool || 0) + cost
  const myStakeAfter = (round.my_stake || 0) + cost
  const sharePct = (myStakeAfter / poolAfter * 100).toFixed(1)

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Add shares · Round #{round.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <p style={{ fontSize: 13, color: 'var(--tx-2)', marginBottom: 12 }}>
            Each share = $5 in the pool
          </p>
          <div className="stepper" style={{ marginBottom: 12 }}>
            <button className="stepper-btn" onClick={() => setShares(Math.max(1, shares - 1))}>−</button>
            <div className="col" style={{ alignItems: 'center' }}>
              <span className="mono" style={{ fontSize: 40, fontWeight: 700 }}>{shares}</span>
              <span style={{ fontSize: 11, color: 'var(--tx-2)' }}>shares</span>
            </div>
            <button className="stepper-btn" onClick={() => setShares(shares + 1)}>+</button>
          </div>
          <div className="row gap-8" style={{ justifyContent: 'center', marginBottom: 16 }}>
            {[1,3,5,10].map(n => (
              <button key={n} onClick={() => setShares(n)} className="chip" style={{
                cursor: 'pointer', border: 0,
                background: shares === n ? 'rgba(46,166,255,.18)' : 'var(--bg-3)',
                color: shares === n ? 'var(--tg)' : 'var(--tx-1)',
              }}>{n}×</button>
            ))}
          </div>
          <div className="card" style={{ marginBottom: 16 }}>
            {[
              ['Cost',          `$${cost.toFixed(2)}`,   null],
              ['Balance before',`$${(user?.credit??0).toFixed(2)}`, 'var(--tx-2)'],
              ['Balance after', `$${after.toFixed(2)}`,  after < 0 ? 'var(--danger)' : 'var(--money)'],
              ['Your pool share',`${sharePct}%`,          null],
            ].map(([k,v,c]) => (
              <div key={k} className="sum-row">
                <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>{k}</span>
                <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: c || '#fff' }}>{v}</span>
              </div>
            ))}
          </div>
          {after < 0
            ? <button className="btn btn-money btn-block">Top up to continue</button>
            : <button className="btn btn-primary btn-block" disabled={busy} onClick={confirm}>
                {busy ? 'Processing…' : `Confirm · $${cost.toFixed(2)}`}
              </button>
          }
        </div>
      </div>
    </div>
  )
}

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

export default function Home({ user, onUserUpdate }) {
  const [round, setRound]   = useState(undefined)
  const [sub, setSub]       = useState(null)
  const [topUp, setTopUp]   = useState(false)
  const [join, setJoin]     = useState(false)
  const [showToast, toastNode] = useToast()

  useEffect(() => {
    api.round().then(d => setRound(d.round)).catch(() => setRound(null))
    api.stripe.subscription().then(r => setSub(r.subscription)).catch(() => {})
  }, [])

  const isLive     = round?.display_status === 'live'
  const myShares   = round?.my_stake ? Math.round(round.my_stake / 5) : 0
  const totalShares= round?.pool     ? Math.round(round.pool / 5) : 0

  return (
    <div className="tab-content">
      {toastNode}

      {/* Greeting + balance */}
      <div style={{ padding: '12px 16px 8px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className="avatar">{getInitials(user.full_name || user.username)}</div>
        <div className="col grow gap-4">
          <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Welcome back</span>
          <span style={{ fontSize: 15, fontWeight: 600 }}>{user.full_name || user.username || 'Player'}</span>
        </div>
        <div className="chip chip-money" onClick={() => setTopUp(true)}
          style={{ cursor: 'pointer', gap: 6 }}>
          <WalletIcon width={13} height={13} />
          <span className="mono">${(user.credit ?? 0).toFixed(2)}</span>
        </div>
      </div>

      {/* Live round hero */}
      {round === undefined ? (
        <div style={{ padding: '40px 0', display: 'flex', justifyContent: 'center' }}>
          <div className="spinner" />
        </div>
      ) : !round ? (
        <div style={{ padding: '8px 16px' }}>
          <div className="jackpot" style={{ textAlign: 'center', padding: '40px 18px' }}>
            <div style={{ fontSize: 40, marginBottom: 10 }}>🎰</div>
            <p style={{ fontWeight: 600, marginBottom: 4 }}>No active round</p>
            <p style={{ fontSize: 13, color: 'var(--tx-2)' }}>The trustee will open one soon!</p>
          </div>
        </div>
      ) : (
        <div style={{ padding: '8px 16px 4px' }}>
          <div className="jackpot">
            <div className="row between" style={{ marginBottom: 14 }}>
              <div className="row gap-8">
                <span className="status-dot live" />
                <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.8px', color: 'var(--money)' }}>
                  {round.display_status === 'live' ? 'LIVE ROUND' : round.display_status === 'closing' ? 'CLOSING SOON' : 'LAST ROUND'}
                </span>
              </div>
              <span className="mono dim" style={{ fontSize: 12 }}>#{round.id}</span>
            </div>

            <div style={{ fontSize: 12, color: 'var(--tx-2)', marginBottom: 2, letterSpacing: '.3px' }}>
              Current pool
            </div>
            <div className="pool-display">
              <span className="cur">$</span>
              <span className="amt">{(round.pool ?? 0).toFixed(0)}</span>
              <span className="unit">CAD</span>
            </div>

            {round.draw_date && (
              <div style={{ margin: '18px 0 14px' }}>
                <Countdown to={round.draw_date + (round.draw_date.includes('T') ? '' : 'T22:30:00')} />
                <div className="row between" style={{ marginTop: 6, fontSize: 11, color: 'var(--tx-3)', whiteSpace: 'nowrap' }}>
                  <span>Draw date</span>
                  <span>{round.draw_date}</span>
                </div>
              </div>
            )}

            <div className="row between" style={{ marginTop: 14 }}>
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
                {round.participants?.length ?? 0} participant{(round.participants?.length ?? 0) !== 1 ? 's' : ''}
              </span>
              {round.my_pct != null && (
                <span className="chip chip-gold">
                  <BoltIcon width={11} height={11} />{round.my_pct}% share
                </span>
              )}
            </div>

            {isLive && (
              <button className="btn btn-primary btn-block" style={{ marginTop: 16 }}
                onClick={() => setJoin(true)}>
                <PlusIcon width={16} height={16} />
                {round.my_stake ? 'Add more shares · $5 each' : 'Join · $5 per share'}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Your stake */}
      {round?.my_stake != null && (
        <>
          <div className="section"><div className="label">Your stake in Round #{round.id}</div></div>
          <div className="stack">
            <div className="card">
              <div className="row between">
                <div className="col gap-4">
                  <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Shares owned</span>
                  <div className="row gap-8" style={{ alignItems: 'baseline' }}>
                    <span className="mono" style={{ fontSize: 26, fontWeight: 700 }}>{myShares}</span>
                    <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>/ {totalShares}</span>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--money)' }}>= ${round.my_stake.toFixed(2)} invested</span>
                </div>
                <div className="col gap-4" style={{ alignItems: 'flex-end' }}>
                  <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Win chance</span>
                  <span className="mono" style={{ fontSize: 26, fontWeight: 700, color: 'var(--gold)' }}>
                    {round.my_pct}%
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>of pool</span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Stats grid */}
      <div className="section"><div className="label">Your stats</div></div>
      <div style={{ padding: '0 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div className="stat">
          <span className="k">Wallet</span>
          <span className="v">${(user.credit ?? 0).toFixed(2)}</span>
          <span className="delta" style={{ color: 'var(--tg)', cursor: 'pointer' }}
            onClick={() => setTopUp(true)}>Tap to top up →</span>
        </div>
        <div className="stat">
          <span className="k">Status</span>
          <span className="v" style={{ fontSize: 16 }}>{user.is_trustee ? 'Trustee' : 'Member'}</span>
          <span className="delta">ID: {user.telegram_id}</span>
        </div>
        {sub && (
          <div className="stat" style={{ gridColumn: 'span 2' }}>
            <span className="k">Monthly plan</span>
            <span className="v" style={{ color: 'var(--money)' }}>${sub.amount}/mo</span>
            {sub.next_billing && <span className="delta">Next charge: {sub.next_billing}</span>}
          </div>
        )}
      </div>

      {/* Refer & earn */}
      <div className="section"><div className="label">Earn free credit</div></div>
      <div className="stack" style={{ marginBottom: 12 }}>
        <div className="card" style={{
          background: 'linear-gradient(135deg, rgba(46,166,255,.08), rgba(78,208,122,.06))',
          borderColor: 'rgba(46,166,255,.2)',
        }}>
          <div className="row gap-12">
            <div style={{
              width: 44, height: 44, borderRadius: 12, flexShrink: 0,
              background: 'rgba(46,166,255,.18)', color: 'var(--tg)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <GiftIcon width={22} height={22} />
            </div>
            <div className="col grow gap-4">
              <span style={{ fontSize: 14, fontWeight: 600 }}>Invite a friend, get $5</span>
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
                Both get $5 credit when they join their first round.
              </span>
            </div>
          </div>
          <button className="btn btn-ghost btn-block btn-sm" style={{ marginTop: 12 }}
            onClick={() => showToast('Share link copied to clipboard', 'success')}>
            <ShareIcon width={14} height={14} /> Share my LOTTOO link
          </button>
        </div>
      </div>

      <TopUpSheet open={topUp} onClose={() => setTopUp(false)}
        onSuccess={(amt, plan) => {
          showToast(plan === 'once' ? `Added $${amt} credit` : `Subscribed · $${amt}/mo`, 'success')
          setTimeout(() => api.me().then(onUserUpdate), 3000)
        }} />

      <JoinSheet open={join} onClose={() => setJoin(false)} round={round} user={user}
        onJoined={(n) => {
          showToast(`Joined with ${n} share${n > 1 ? 's' : ''}!`, 'success')
          api.round().then(d => setRound(d.round))
          api.me().then(onUserUpdate)
        }} />
    </div>
  )
}
