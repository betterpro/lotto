import { useState, useEffect } from 'react'
import { api } from '../api.js'
import { TicketIcon, TrophyIcon } from '../components/Icon.jsx'
import { StatusPill } from '../components/StatusPill.jsx'

function TicketPhotoModal({ roundId, onClose }) {
  const [src, setSrc] = useState(null)
  const [err, setErr] = useState(false)

  useEffect(() => {
    const initData = window.Telegram?.WebApp?.initData ?? ''
    fetch(`/api/round/${roundId}/ticket-image`, {
      headers: { 'X-Init-Data': initData },
    }).then(r => {
      if (!r.ok) throw new Error()
      return r.blob()
    }).then(blob => setSrc(URL.createObjectURL(blob)))
      .catch(() => setErr(true))
    return () => src && URL.revokeObjectURL(src)
  }, [roundId])

  return (
    <div className="sheet-overlay" onClick={onClose}
      style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 420, borderRadius: 16, overflow: 'hidden', background: 'var(--surface)' }}>
        <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>Ticket · Round #{roundId}</span>
          <button onClick={onClose} style={{ background: 'var(--bg-3)', border: 'none', borderRadius: '50%',
            width: 28, height: 28, cursor: 'pointer', color: 'var(--tx-2)', fontSize: 14 }}>✕</button>
        </div>
        {err ? (
          <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--tx-2)', fontSize: 13 }}>
            Image not available
          </div>
        ) : !src ? (
          <div style={{ padding: '40px 16px', display: 'flex', justifyContent: 'center' }}>
            <div className="spinner" />
          </div>
        ) : (
          <img src={src} alt="Lotto ticket" style={{ width: '100%', display: 'block' }} />
        )}
      </div>
    </div>
  )
}

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function fmtBig(n) {
  if (!n) return '—'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(0) + 'M'
  if (n >= 1_000)     return (n / 1_000).toFixed(0) + 'K'
  return String(n)
}

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s.includes('T') ? s : s + 'T00:00:00')
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

const FILTERS = ['All', 'Live', 'Drawn', 'Won']

function RoundCard({ round }) {
  const [showPhoto, setShowPhoto] = useState(false)
  const ds = round.display_status || round.status
  const isOpen     = ['OPEN','live','open'].includes(ds)
  const isUploaded = ['UPLOADED','CLOSING','uploaded','closed'].includes(ds)
  const isDrawn    = ['DRAWN','done','drawn'].includes(ds)
  const hasWon     = (round.my_prize || 0) > 0
  const myStake    = (round.my_shares || 0) * (round.price_per_share || 5)

  const iconBg    = isOpen ? 'rgba(78,208,122,.14)' : isUploaded ? 'rgba(242,163,59,.14)' :
    hasWon ? 'rgba(245,199,59,.14)' : 'var(--bg-3)'
  const iconColor = isOpen ? 'var(--money)' : isUploaded ? 'var(--warn)' :
    hasWon ? 'var(--gold)' : 'var(--tx-2)'

  return (
    <div className="round-card">
      <div className="row between" style={{ marginBottom: 8 }}>
        <div className="row gap-10">
          <div style={{
            width: 38, height: 38, borderRadius: 10,
            background: iconBg, color: iconColor,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            {isDrawn && hasWon
              ? <TrophyIcon width={20} height={20} />
              : <TicketIcon width={20} height={20} />}
          </div>
          <div className="col gap-4">
            <span style={{ fontSize: 15, fontWeight: 600 }}>Round #{round.id}</span>
            <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
              {fmtDate(round.draw_date)} · ${fmtBig(round.jackpot)} jackpot
            </span>
          </div>
        </div>
        <StatusPill status={ds} />
      </div>

      <div style={{ height: '.5px', background: 'var(--hairline)', margin: '6px 0 10px' }} />

      <div className="row between">
        <div className="row gap-12">
          <div className="col gap-4">
            <span style={{ fontSize: 11, color: 'var(--tx-3)', letterSpacing: '.3px' }}>STAKE</span>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
              {round.my_shares ? fmtCAD(myStake) : '—'}
            </span>
          </div>
          <div className="col gap-4">
            <span style={{ fontSize: 11, color: 'var(--tx-3)', letterSpacing: '.3px' }}>SHARES</span>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
              {round.my_shares ?? '—'} / {round.participants ?? 0}
            </span>
          </div>
          <div className="col gap-4">
            <span style={{ fontSize: 11, color: 'var(--tx-3)', letterSpacing: '.3px' }}>POOL</span>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
              {fmtCAD(round.pool)}
            </span>
          </div>
        </div>

        {isDrawn && (
          <div className="col" style={{ alignItems: 'flex-end', gap: 2 }}>
            {hasWon ? (
              <>
                <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: 'var(--money)' }}>
                  +{fmtCAD(round.my_prize)}
                </span>
                <span style={{ fontSize: 10, color: 'var(--money)' }}>Won</span>
              </>
            ) : (
              <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>No prize</span>
            )}
          </div>
        )}

        {isOpen && !round.my_shares && (
          <div className="col" style={{ alignItems: 'flex-end' }}>
            <span className="chip chip-tg" style={{ padding: '4px 10px' }}>LIVE ›</span>
          </div>
        )}
      </div>

      {round.has_ticket_image && (
        <>
          <div style={{ height: '.5px', background: 'var(--hairline)', margin: '10px 0 8px' }} />
          <button onClick={() => setShowPhoto(true)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer', padding: 0,
              display: 'flex', alignItems: 'center', gap: 6,
              color: 'var(--tg)', fontSize: 12, fontWeight: 600,
            }}>
            📎 View ticket photo
          </button>
        </>
      )}

      {showPhoto && <TicketPhotoModal roundId={round.id} onClose={() => setShowPhoto(false)} />}
    </div>
  )
}

export default function Rounds() {
  const [rounds, setRounds] = useState(null)
  const [filter, setFilter] = useState('All')

  useEffect(() => {
    api.rounds().then(d => setRounds(d.rounds || [])).catch(() => setRounds([]))
  }, [])

  if (rounds === null) return (
    <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  if (rounds.length === 0) return (
    <div className="empty">
      <span style={{ fontSize: 48 }}>🎟</span>
      <span className="e-title">No rounds yet</span>
      <span className="e-sub">Rounds appear here once an admin opens the first draw.</span>
    </div>
  )

  const myRounds    = rounds.filter(r => r.my_shares)
  const totalWon    = rounds.reduce((a, r) => a + (r.my_prize || 0), 0)
  const totalStaked = myRounds.reduce((a, r) => a + (r.my_shares || 0) * (r.price_per_share || 5), 0)
  const net = totalWon - totalStaked

  const filtered = rounds.filter(r => {
    const ds = r.display_status || r.status
    if (filter === 'All')   return true
    if (filter === 'Live')  return ['OPEN','CLOSING','UPLOADED','live','open','uploaded','closed'].includes(ds)
    if (filter === 'Drawn') return ['DRAWN','done','drawn'].includes(ds)
    if (filter === 'Won')   return (r.my_prize || 0) > 0
    return true
  })

  return (
    <div className="tab-content">
      <div style={{ padding: '10px 16px 6px' }}>
        <div className="card" style={{ background: 'linear-gradient(135deg, #1f2c3a, #1a2531)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <div className="col gap-4">
              <span style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Played</span>
              <span className="mono" style={{ fontSize: 20, fontWeight: 700 }}>{myRounds.length}</span>
              <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>rounds joined</span>
            </div>
            <div className="col gap-4" style={{ borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 }}>
              <span style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Won</span>
              <span className="mono" style={{ fontSize: 20, fontWeight: 700, color: 'var(--money)' }}>{fmtCAD(totalWon)}</span>
              <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>in prizes</span>
            </div>
            <div className="col gap-4" style={{ borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 }}>
              <span style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Net</span>
              <span className="mono" style={{ fontSize: 20, fontWeight: 700, color: net >= 0 ? 'var(--money)' : 'var(--danger)' }}>
                {net >= 0 ? '+' : ''}{fmtCAD(net)}
              </span>
              <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>{fmtCAD(totalStaked)} staked</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ padding: '12px 16px 6px', display: 'flex', gap: 8, overflowX: 'auto' }}>
        {FILTERS.map(f => (
          <button key={f}
            className={'filter-chip ' + (filter === f ? 'active' : 'inactive')}
            onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
      </div>

      <div style={{ padding: '6px 16px 16px' }}>
        {filtered.length === 0 ? (
          <div className="empty" style={{ paddingTop: 40 }}>
            <span style={{ fontSize: 36 }}>🔍</span>
            <span className="e-sub">No {filter.toLowerCase()} rounds</span>
          </div>
        ) : filtered.map(r => (
          <RoundCard key={r.id} round={r} />
        ))}
      </div>
    </div>
  )
}
