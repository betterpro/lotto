import { useState, useEffect } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { WalletIcon, TicketIcon, TrophyIcon, ArrowDownIcon, BoltIcon } from '../components/Icon.jsx'

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function fmtTime(s) {
  if (!s) return ''
  const d = new Date(s)
  return d.toLocaleTimeString('en-CA', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function fmtDay(s) {
  if (!s) return ''
  const d    = new Date(s.includes('T') ? s : s + 'T00:00:00')
  const now  = new Date()
  const diff = Math.floor((now - d) / 86400000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: d.getFullYear() !== now.getFullYear() ? 'numeric' : undefined })
}

function groupByDay(txs) {
  const map = new Map()
  txs.forEach(tx => {
    const key = (tx.created_at || '').slice(0, 10)
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(tx)
  })
  return [...map.entries()]
}

const TX_META = {
  deposit:     { icon: WalletIcon,  color: 'var(--money)', sign: '+', label: 'Top-up'         },
  win:         { icon: TrophyIcon,  color: 'var(--gold)',  sign: '+', label: 'Prize won'       },
  refund:      { icon: ArrowDownIcon, color: 'var(--tg)',  sign: '+', label: 'Refund'          },
  participate: { icon: TicketIcon,  color: 'var(--tx-3)', sign: '−', label: 'Joined round'    },
  withdraw:    { icon: WalletIcon,  color: 'var(--danger)',sign: '−', label: 'Withdrawal'      },
}

const FILTERS = [
  { id: 'all',         label: 'All'       },
  { id: 'deposit',     label: 'Top-ups'   },
  { id: 'participate', label: 'Joins'     },
  { id: 'win',         label: 'Wins'      },
]

export default function History() {
  const showToast = useToast()
  const [txs,    setTxs]    = useState(null)
  const [filter, setFilter] = useState('all')
  const [sub,    setSub]    = useState(null)

  useEffect(() => {
    api.transactions().then(d => setTxs(d.transactions)).catch(() => setTxs([]))
    api.stripe.subscription().then(r => setSub(r.subscription)).catch(() => {})
  }, [])

  async function cancelSub() {
    try {
      if (sub?.cancel_at_period_end) {
        showToast('Contact support to reactivate your subscription.', 'warn')
      } else {
        await api.stripe.cancelSub()
        setSub(s => s ? { ...s, cancel_at_period_end: true } : s)
        showToast('Subscription will cancel at period end', 'success')
      }
    } catch (e) { showToast(e.message, 'error') }
  }

  if (txs === null) return (
    <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  if (txs.length === 0) return (
    <div className="empty">
      <span style={{ fontSize: 48 }}>📋</span>
      <span className="e-title">No activity yet</span>
      <span className="e-sub">Your top-ups, round joins, and wins will appear here.</span>
    </div>
  )

  const filtered = filter === 'all' ? txs : txs.filter(t => t.type === filter)

  const totalIn  = txs.filter(t => ['deposit','win','refund'].includes(t.type)).reduce((a, t) => a + (t.amount || 0), 0)
  const totalOut = txs.filter(t => ['participate','withdraw'].includes(t.type)).reduce((a, t) => a + (t.amount || 0), 0)
  const totalWon = txs.filter(t => t.type === 'win').reduce((a, t) => a + (t.amount || 0), 0)

  const grouped = groupByDay(filtered)

  return (
    <div className="tab-content">
      {/* Summary row */}
      <div style={{ padding: '10px 16px 0' }}>
        <div className="card" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 0 }}>
          {[
            ['Added',  fmtCAD(totalIn),  'var(--money)'],
            ['Spent',  fmtCAD(Math.abs(totalOut)), 'var(--tx-2)'],
            ['Won',    fmtCAD(totalWon), 'var(--gold)'],
          ].map(([k, v, c], i) => (
            <div key={k} className="col gap-4" style={i ? { borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 } : {}}>
              <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{k}</span>
              <span className="mono" style={{ fontSize: 17, fontWeight: 700, color: c }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Filter chips */}
      <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8, overflowX: 'auto' }}>
        {FILTERS.map(f => (
          <button key={f.id}
            onClick={() => setFilter(f.id)}
            style={{
              flexShrink: 0, padding: '5px 14px', borderRadius: 20,
              fontSize: 13, fontWeight: 600, border: 'none', cursor: 'pointer',
              background: filter === f.id ? 'var(--tg)' : 'var(--surface-2)',
              color: filter === f.id ? '#fff' : 'var(--tx-2)',
            }}>
            {f.label}
          </button>
        ))}
      </div>

      {/* Activity list */}
      <div style={{ padding: '12px 16px 24px' }}>
        {filtered.length === 0 ? (
          <div className="empty" style={{ paddingTop: 40 }}>
            <span style={{ fontSize: 36 }}>🔍</span>
            <span className="e-sub">No {FILTERS.find(f => f.id === filter)?.label.toLowerCase()} yet</span>
          </div>
        ) : grouped.map(([day, items]) => (
          <div key={day}>
            <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, letterSpacing: '.5px',
                          textTransform: 'uppercase', marginBottom: 8, marginTop: 12 }}>
              {fmtDay(items[0].created_at)}
            </div>
            <div className="card" style={{ padding: 0 }}>
              {items.map((tx, idx) => {
                const meta = TX_META[tx.type] ?? { icon: WalletIcon, color: 'var(--tx-3)', sign: '', label: tx.type }
                const IconComp = meta.icon
                const pos = meta.sign === '+'
                return (
                  <div key={tx.id} className="act-row" style={idx < items.length - 1 ? { borderBottom: '.5px solid var(--hairline)' } : {}}>
                    <div className="act-icon" style={{ background: pos ? `${meta.color}18` : 'var(--bg-3)', color: meta.color }}>
                      <IconComp width={16} height={16} />
                    </div>
                    <div className="col grow" style={{ minWidth: 0 }}>
                      <span style={{ fontSize: 15, fontWeight: 500 }}>{tx.note || meta.label}</span>
                      <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>{fmtTime(tx.created_at)}</span>
                    </div>
                    <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: pos ? meta.color : 'var(--tx-1)', flexShrink: 0 }}>
                      {meta.sign}{fmtCAD(Math.abs(tx.amount))}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Subscription section */}
      {sub && (
        <>
          <div className="section"><div className="label">Subscription</div></div>
          <div style={{padding:'0 16px 16px'}}>
            <div className="card" style={{borderColor:'rgba(78,208,122,.25)'}}>
              <div className="row between">
                <div className="row gap-12">
                  <div style={{width:40,height:40,borderRadius:10,background:'rgba(78,208,122,.14)',color:'var(--money)',display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
                    <BoltIcon width={20} height={20}/>
                  </div>
                  <div className="col">
                    <span style={{fontWeight:600}}>${sub.amount}/month plan</span>
                    <span style={{fontSize: 13,color:'var(--tx-2)'}}>
                      {sub.next_billing ? `Renews ${sub.next_billing}` : 'Active subscription'}
                    </span>
                  </div>
                </div>
                <span className="chip chip-money">ACTIVE</span>
              </div>
              <div className="row gap-8" style={{marginTop:12}}>
                <button className="btn btn-sm btn-ghost" style={{flex:1}} onClick={cancelSub}>
                  {sub.cancel_at_period_end ? 'Reactivate' : 'Cancel'}
                </button>
                <button className="btn btn-sm btn-ghost" style={{flex:1}}>Manage</button>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
