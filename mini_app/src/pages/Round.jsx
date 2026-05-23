import { useState, useEffect } from 'react'
import { api } from '../api.js'
import { StatusPill } from '../components/StatusPill.jsx'
import { TrophyIcon, TicketIcon } from '../components/Icon.jsx'

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function drawLabel(s) {
  if (!s) return null
  const today = new Date(); today.setHours(0,0,0,0)
  const draw  = new Date(s.includes('T') ? s : s + 'T00:00:00')
  const diff  = Math.round((draw - today) / 86400000)
  if (diff === 0) return 'Draw today'
  if (diff === 1) return 'Draw tomorrow'
  if (diff > 1)  return `Draw in ${diff} days`
  return `Drawn ${-diff}d ago`
}

function RoundDetail({ round, onClose }) {
  const ds = round.display_status
  const isDone = ds === 'done'

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Round #{round.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <div className="row between" style={{ marginBottom: 16 }}>
            <div className="col gap-4">
              <span style={{ fontSize: 11, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>Pool</span>
              <span className="mono" style={{ fontSize: 24, fontWeight: 700, color: 'var(--gold)' }}>
                {fmtCAD(round.pool)}
              </span>
            </div>
            <StatusPill status={ds} />
          </div>

          {isDone && round.winner_name && (
            <div className="card" style={{ marginBottom: 12, textAlign: 'center', borderColor: 'rgba(245,199,59,.3)' }}>
              <div style={{ fontSize: 32, marginBottom: 6 }}>🏆</div>
              <div style={{ fontWeight: 700, fontSize: 18 }}>{round.winner_name}</div>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 4 }}>Winner · took the pool</div>
            </div>
          )}

          {round.my_stake != null && (
            <>
              <div className="label" style={{ marginTop: 12 }}>Your stake</div>
              <div className="card" style={{ marginBottom: 16 }}>
                {[
                  ['Invested',    fmtCAD(round.my_stake),    null],
                  ['Win chance',  `${round.my_pct}%`,         null],
                  isDone ? ['Result', round.my_won ? `🏆 Winner!` : 'No prize',
                            round.my_won ? 'var(--money)' : 'var(--tx-3)'] : null,
                ].filter(Boolean).map(([k, v, c]) => (
                  <div key={k} className="sum-row">
                    <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>{k}</span>
                    <span className="mono" style={{ fontSize: 14, fontWeight: 600, color: c || '#fff' }}>{v}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="label">All participants</div>
          <div className="card">
            {(round.participants || []).map(p => (
              <div key={p.user_id} style={{ marginBottom: 12 }}>
                <div className="row between">
                  <span style={{ fontWeight: 500 }}>{p.won ? '🏆 ' : ''}{p.full_name}</span>
                  <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>{p.pct}%</span>
                </div>
                <div className="bar" style={{ marginTop: 4 }}>
                  <span style={{ width: `${p.pct}%` }} />
                </div>
                <div style={{ fontSize: 11, color: 'var(--tx-3)', marginTop: 2 }}>{fmtCAD(p.amount)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Round() {
  const [data, setData]     = useState(undefined)
  const [detail, setDetail] = useState(false)

  useEffect(() => {
    api.round().then(d => setData(d.round)).catch(() => setData(null))
  }, [])

  if (data === undefined) return (
    <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  if (!data) return (
    <div className="empty">
      <span style={{ fontSize: 48 }}>🎰</span>
      <span className="e-title">No active round</span>
      <span className="e-sub">The trustee will open one soon!</span>
    </div>
  )

  const { id, display_status: ds, pool, draw_date, participants, my_stake, my_pct, my_won, winner_name } = data
  const isDone   = ds === 'done'
  const isLive   = ds === 'live'
  const myShares = my_stake ? Math.round(my_stake / 5) : 0

  return (
    <div className="tab-content">
      {/* Summary card */}
      <div style={{ padding: '10px 16px 6px' }}>
        <div className="card" style={{ background: 'linear-gradient(135deg, #1f2c3a, #1a2531)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            {[
              ['Pool',    fmtCAD(pool),             'CAD'],
              ['Players', participants.length,       'participants'],
              ['My stake',my_stake ? fmtCAD(my_stake) : '—',
               myShares > 0 ? `${myShares} share${myShares !== 1 ? 's' : ''}` : 'not joined'],
            ].map(([k, v, sub], i) => (
              <div key={k} className="col gap-4" style={i ? { borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 } : {}}>
                <span style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>{k}</span>
                <span className="mono" style={{ fontSize: 18, fontWeight: 700, color: i === 2 && my_stake ? 'var(--money)' : undefined }}>{v}</span>
                <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>{sub}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Round card */}
      <div style={{ padding: '6px 16px 16px' }}>
        <div className="round-row" onClick={() => setDetail(true)}>
          <div className="row between" style={{ marginBottom: 8 }}>
            <div className="row gap-10">
              <div style={{
                width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                background: isDone && my_won ? 'rgba(245,199,59,.14)' : isLive ? 'rgba(78,208,122,.14)' : 'var(--bg-3)',
                color: isDone && my_won ? 'var(--gold)' : isLive ? 'var(--money)' : 'var(--tx-2)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {isDone && my_won ? <TrophyIcon width={20} height={20} /> : <TicketIcon width={20} height={20} />}
              </div>
              <div className="col">
                <span style={{ fontSize: 15, fontWeight: 600 }}>Round #{id}</span>
                <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
                  {draw_date ? drawLabel(draw_date) + ' · ' : ''}{fmtCAD(pool)} pool
                </span>
              </div>
            </div>
            <StatusPill status={ds} />
          </div>

          <div style={{ height: '.5px', background: 'var(--hairline)', margin: '6px 0 10px' }} />

          <div className="row between">
            <div className="row gap-12">
              {my_stake != null && (
                <div className="col">
                  <span style={{ fontSize: 11, color: 'var(--tx-3)', letterSpacing: '.3px' }}>STAKE</span>
                  <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{fmtCAD(my_stake)}</span>
                </div>
              )}
              {my_pct != null && (
                <div className="col">
                  <span style={{ fontSize: 11, color: 'var(--tx-3)', letterSpacing: '.3px' }}>CHANCE</span>
                  <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{my_pct}%</span>
                </div>
              )}
            </div>
            {isDone
              ? my_won
                ? <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--money)' }}>🏆 Won!</span>
                : winner_name
                  ? <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>Won by {winner_name}</span>
                  : <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>Drawn</span>
              : isLive && !my_stake
                ? <span className="chip chip-tg">JOIN ›</span>
                : null
            }
          </div>
        </div>

        <p style={{ fontSize: 12, color: 'var(--tx-3)', textAlign: 'center', marginTop: 8 }}>
          Tap the round card for full details
        </p>
      </div>

      {detail && <RoundDetail round={data} onClose={() => setDetail(false)} />}
    </div>
  )
}
