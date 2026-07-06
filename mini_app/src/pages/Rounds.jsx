import { useState, useEffect } from 'react'
import { api } from '../api.js'
import { TicketIcon, TrophyIcon } from '../components/Icon.jsx'
import { StatusPill } from '../components/StatusPill.jsx'
import { AgreementLink, downloadGroupPlayForm } from '../components/AgreementSheet.jsx'
import { Ball } from '../components/Ball.jsx'
import { jackpotDisplay } from '../lottery.js'

function parseWinning(round) {
  let main = []
  try { main = JSON.parse(round?.winning_numbers || '[]') } catch { main = [] }
  const bonus = round?.bonus_number != null ? Number(round.bonus_number) : null
  return { mainSet: new Set(main.map(Number)), main, bonus }
}

function TicketNumbersModal({ round, onClose }) {
  const tickets = round.tickets_breakdown || []
  const { mainSet, main, bonus } = parseWinning(round)
  const hasResults = main.length > 0
  const fmt = n => '$' + Number(n || 0).toFixed(2)
  const totalPrize = tickets.reduce((a, t) => a + (Number(t.prize) || 0), 0)
  const totalFree  = tickets.reduce((a, t) => a + (Number(t.free) || 0), 0)
  const winningTickets = tickets.filter(t => t.won).length

  return (
    <div className="sheet-overlay" onClick={onClose}
      style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 440, maxHeight: '90vh', overflowY: 'auto',
          borderRadius: 16, background: 'var(--surface)' }}>
        <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1,
          borderBottom: '.5px solid var(--hairline)' }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>
            Ticket numbers · Round #{round.group_seq ?? round.id}
          </span>
          <button onClick={onClose} style={{ background: 'var(--bg-3)', border: 'none', borderRadius: '50%',
            width: 28, height: 28, cursor: 'pointer', color: 'var(--tx-2)', fontSize: 15 }}>✕</button>
        </div>

        <div className="col" style={{ gap: 12, padding: 16 }}>
          {hasResults && (
            <div className="card" style={{ padding: 12, background: 'var(--bg-3)' }}>
              <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, textTransform: 'uppercase',
                letterSpacing: '.3px', marginBottom: 8 }}>Winning numbers</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {main.map((n, i) => <Ball key={i} n={n} match size="md" />)}
                {bonus != null && (<>
                  <span style={{ color: 'var(--tx-3)', fontSize: 17, fontWeight: 700 }}>+</span>
                  <Ball n={bonus} bonus size="md" />
                </>)}
              </div>
            </div>
          )}

          {hasResults && (totalPrize > 0 || totalFree > 0) && (
            <div className="card" style={{ padding: 12, border: '.5px solid rgba(245,199,59,.4)',
              background: 'rgba(245,199,59,.08)' }}>
              <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, textTransform: 'uppercase',
                letterSpacing: '.3px', marginBottom: 6 }}>Round result</div>
              <div className="row between" style={{ alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
                  {winningTickets} winning ticket{winningTickets === 1 ? '' : 's'}
                </span>
                <div className="row gap-8" style={{ alignItems: 'center' }}>
                  {totalPrize > 0 && (
                    <span style={{ fontSize: 17, fontWeight: 800, color: 'var(--money)' }}>{fmt(totalPrize)}</span>
                  )}
                  {totalFree > 0 && (
                    <span className="chip chip-gold" style={{ fontSize: 11, padding: '2px 8px' }}>
                      🎁 {totalFree} free</span>
                  )}
                </div>
              </div>
              {round.my_prize > 0 && (
                <div className="row between" style={{ marginTop: 8, paddingTop: 8,
                  borderTop: '.5px solid rgba(245,199,59,.3)', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Your share</span>
                  <span style={{ fontSize: 15, fontWeight: 800, color: 'var(--money)' }}>{fmt(round.my_prize)}</span>
                </div>
              )}
            </div>
          )}

          {tickets.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--tx-2)', fontSize: 14, padding: '24px 0' }}>
              Ticket numbers aren’t available yet.
            </div>
          ) : tickets.map((t, ti) => (
            <div key={ti} className="card" style={{ padding: 12,
              border: `.5px solid ${t.won ? 'rgba(245,199,59,.5)' : 'var(--hairline)'}` }}>
              <div className="row between" style={{ alignItems: 'center', marginBottom: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>Ticket {ti + 1}</span>
                <div className="row gap-8" style={{ alignItems: 'center' }}>
                  {hasResults && (
                    <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>best {t.best_label}</span>
                  )}
                  {t.won
                    ? <span className="chip chip-gold" style={{ fontSize: 11, padding: '2px 8px' }}>WON</span>
                    : hasResults ? <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>No win</span> : null}
                </div>
              </div>
              <div className="col" style={{ gap: 8 }}>
                {(t.lines || []).map((ln, li) => (
                  <div key={li} style={{ display: 'flex', gap: 5, flexWrap: 'wrap', alignItems: 'center' }}>
                    {(ln.numbers || []).map((n, ni) => (
                      <Ball key={ni} n={n}
                        match={mainSet.has(Number(n))}
                        bonus={bonus != null && Number(n) === bonus && !mainSet.has(Number(n))}
                        size="sm" />
                    ))}
                    {ln.win && (
                      <span style={{ fontSize: 11, color: 'var(--money)', fontWeight: 700, marginLeft: 2 }}>✓ win</span>
                    )}
                  </div>
                ))}
              </div>
              {(t.prize > 0 || t.free > 0) && (
                <div className="row gap-8" style={{ marginTop: 10, paddingTop: 8,
                  borderTop: '.5px solid var(--hairline)', fontSize: 13 }}>
                  {t.prize > 0 && <span style={{ color: 'var(--money)', fontWeight: 700 }}>{fmt(t.prize)} prize</span>}
                  {t.free > 0 && <span className="chip chip-gold" style={{ fontSize: 11, padding: '2px 8px' }}>
                    🎁 {t.free} free ticket{t.free === 1 ? '' : 's'}</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function TicketPhotoModal({ round, onClose }) {
  // Render the stored ticket image(s) directly. round_tickets[].image are public
  // Supabase URLs (or data URIs) that an <img> can show without auth/CORS — unlike
  // fetching the auth-protected endpoint, which fails on a cross-origin redirect.
  const imgs = round.ticket_images?.length
    ? round.ticket_images
    : (round.round_tickets || []).map(t => t?.image).filter(Boolean)
  const sources = imgs.length
    ? imgs
    : [`${import.meta.env.VITE_API_BASE ?? ''}/api/round/${round.id}/ticket-image`]
  const [failed, setFailed] = useState({})
  const allFailed = sources.every((_, i) => failed[i])

  return (
    <div className="sheet-overlay" onClick={onClose}
      style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 420, maxHeight: '90vh', overflowY: 'auto',
          borderRadius: 16, background: 'var(--surface)' }}>
        <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1 }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>
            Ticket{sources.length > 1 ? 's' : ''} · Round #{round.group_seq ?? round.id}
          </span>
          <button onClick={onClose} style={{ background: 'var(--bg-3)', border: 'none', borderRadius: '50%',
            width: 28, height: 28, cursor: 'pointer', color: 'var(--tx-2)', fontSize: 15 }}>✕</button>
        </div>
        {allFailed ? (
          <div style={{ padding: '40px 16px', textAlign: 'center', color: 'var(--tx-2)', fontSize: 14 }}>
            Image not available
          </div>
        ) : (
          <div className="col" style={{ gap: 8, padding: '0 12px 12px' }}>
            {sources.map((src, i) => (
              failed[i] ? null : (
                <a key={i} href={src} target="_blank" rel="noreferrer" style={{ display: 'block' }}>
                  <img src={src} alt={`Ticket ${i + 1}`} loading="lazy"
                    onError={() => setFailed(f => ({ ...f, [i]: true }))}
                    style={{ width: '100%', display: 'block', borderRadius: 10 }} />
                </a>
              )
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function fmtDollarInt(n) {
  return '$' + Math.round(Number(n || 0)).toLocaleString('en-CA')
}

// Show cents when the amount isn't a whole dollar (so $4.50 doesn't read as $5).
function fmtMoney(n) {
  const v = Number(n || 0)
  return Number.isInteger(v) ? '$' + v.toLocaleString('en-CA') : fmtCAD(v)
}

function ParticipantsModal({ round, onClose }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  useEffect(() => {
    api.rounds.participants(round.id).then(setData).catch(e => setErr(e.message || 'Could not load'))
  }, [round.id])

  return (
    <div className="sheet-overlay" onClick={onClose}
      style={{ alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 440, maxHeight: '90vh', overflowY: 'auto',
          borderRadius: 16, background: 'var(--surface)' }}>
        <div style={{ padding: '12px 16px', display: 'flex', justifyContent: 'space-between',
          alignItems: 'center', position: 'sticky', top: 0, background: 'var(--surface)', zIndex: 1,
          borderBottom: '.5px solid var(--hairline)' }}>
          <span style={{ fontWeight: 700, fontSize: 16 }}>
            Pool breakdown · Round #{round.group_seq ?? round.id}
          </span>
          <button onClick={onClose} style={{ background: 'var(--bg-3)', border: 'none', borderRadius: '50%',
            width: 28, height: 28, cursor: 'pointer', color: 'var(--tx-2)', fontSize: 15 }}>✕</button>
        </div>

        {err ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--tx-2)', fontSize: 14 }}>{err}</div>
        ) : !data ? (
          <div style={{ padding: 40, display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
        ) : (
          <div className="col" style={{ gap: 0, padding: '8px 16px 16px' }}>
            <div className="row between" style={{ padding: '10px 0', borderBottom: '.5px solid var(--hairline)' }}>
              <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>{data.count} participant{data.count === 1 ? '' : 's'}</span>
              <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>Total pool <b style={{ color: 'var(--tx-1)' }}>{fmtMoney(data.pool)}</b></span>
            </div>
            {(data.participants || []).map((p, i) => (
              <div key={i} className="row between" style={{ alignItems: 'center', padding: '11px 0',
                borderBottom: '.5px solid var(--hairline)' }}>
                <div className="col" style={{ gap: 2 }}>
                  <span style={{ fontSize: 14, fontWeight: p.is_me ? 700 : 500,
                    color: p.is_me ? 'var(--tg)' : 'var(--tx-1)' }}>{p.label}</span>
                  {p.free_value > 0 && (
                    <span style={{ fontSize: 11.5, color: 'var(--money)', fontWeight: 600 }}>
                      🎁 {fmtCAD(p.free_value)} free
                    </span>
                  )}
                </div>
                <div className="col" style={{ alignItems: 'flex-end', gap: 2 }}>
                  <span className="mono" style={{ fontSize: 14, fontWeight: 700 }}>{fmtMoney(p.amount)}</span>
                  <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>{p.pct}%</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
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

function playerCount(round) {
  if (!round) return 0
  if (Array.isArray(round.participants)) return round.participants.length
  const n = round.participants_count ?? round.participants
  return typeof n === 'number' ? n : 0
}

function RoundCard({ round }) {
  const [showPhoto, setShowPhoto] = useState(false)
  const [showNumbers, setShowNumbers] = useState(false)
  const [showPool, setShowPool] = useState(false)
  const hasNumbers = (round.tickets_breakdown || []).length > 0
  const ds = round.display_status || round.status
  const isRally    = ['RALLY','OPEN','live','open'].includes(ds)
  const isLocked   = ds === 'LOCKED'
  const isRevealed = ds === 'REVEALED'
  const isWon      = ds === 'WON'
  const isLost     = ds === 'LOST'

  const iconBg    = isWon ? 'rgba(245,199,59,.2)' : isRally ? 'rgba(78,208,122,.14)' :
    isLocked ? 'rgba(242,163,59,.14)' : isLost ? 'var(--bg-3)' : 'rgba(46,166,255,.12)'
  const iconColor = isWon ? '#ffe566' : isRally ? 'var(--money)' :
    isLocked ? 'var(--warn)' : isLost ? 'var(--tx-3)' : 'var(--tg)'

  return (
    <div className="round-card">
      <div className="row between" style={{ marginBottom: 8 }}>
        <div className="row gap-10">
          <div style={{
            width: 38, height: 38, borderRadius: 10,
            background: iconBg, color: iconColor,
            display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
          }}>
            {isWon
              ? <TrophyIcon width={20} height={20} />
              : <TicketIcon width={20} height={20} />}
          </div>
          <div className="col gap-4">
            <span style={{ fontSize: 16, fontWeight: 600 }}>Round #{round.group_seq ?? round.id}</span>
            <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
              {fmtDate(round.draw_date)} · {jackpotDisplay(round.jackpot, { suffix: ' jackpot' })}
            </span>
          </div>
        </div>
        <StatusPill status={ds} />
      </div>

      <div style={{ height: '.5px', background: 'var(--hairline)', margin: '6px 0 10px' }} />

      <div className="row between">
        <div className="row gap-12">
          <div className="col gap-4">
            <span style={{ fontSize: 12, color: 'var(--tx-3)', letterSpacing: '.3px' }}>YOUR STAKE</span>
            <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
              {round.my_stake ? fmtMoney(round.my_stake) : '—'}
            </span>
            {round.my_free_value > 0 && (
              <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--money)' }}>
                🎁 {fmtCAD(round.my_free_value)} free
              </span>
            )}
          </div>
          <div className="col gap-4">
            <span style={{ fontSize: 12, color: 'var(--tx-3)', letterSpacing: '.3px' }}>YOUR SHARE</span>
            <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
              {round.my_pct != null ? `${round.my_pct}%` : '—'}
            </span>
            <span style={{ fontSize: 11.5, color: 'var(--tx-3)' }}>of {fmtMoney(round.pool)}</span>
          </div>
        </div>

        {(isRevealed || isWon || isLost) && (
          <div className="col" style={{ alignItems: 'flex-end', gap: 2 }}>
            {isWon ? (
              <>
                <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: 'var(--money)' }}>
                  +{fmtMoney(round.my_prize)}
                </span>
                <span style={{ fontSize: 12, color: 'var(--money)' }}>Won</span>
              </>
            ) : round.my_free_won > 0 ? (
              <>
                <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: 'var(--gold)' }}>
                  🎁 {fmtMoney(round.my_free_won)}
                </span>
                <span style={{ fontSize: 12, color: 'var(--gold)' }}>Free tickets</span>
              </>
            ) : (
              <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>No prize</span>
            )}
          </div>
        )}

        {isRally && !round.my_shares && (
          <div className="col" style={{ alignItems: 'flex-end' }}>
            <span className="chip chip-tg" style={{ padding: '4px 10px' }}>JOIN ›</span>
          </div>
        )}
      </div>

      {(round.my_shares > 0 || round.my_stake) && (
        <div style={{ marginTop: 10 }}>
          <AgreementLink
            kind="round"
            roundId={round.id}
            label="Round draw agreement"
            disabled={!round.agreement_available}
            disabledHint="Available when entries close (1 day before draw)"
          />
        </div>
      )}

      {(round.has_ticket_image || hasNumbers || playerCount(round) > 0) && (
        <>
          <div style={{ height: '.5px', background: 'var(--hairline)', margin: '10px 0 8px' }} />
          <div className="row gap-16" style={{ flexWrap: 'wrap' }}>
            {playerCount(round) > 0 && (
              <button onClick={() => setShowPool(true)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: 'var(--tg)', fontSize: 13, fontWeight: 600,
                }}>
                👥 Pool breakdown ({playerCount(round)})
              </button>
            )}
            {hasNumbers && (
              <button onClick={() => setShowNumbers(true)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: 'var(--tg)', fontSize: 13, fontWeight: 600,
                }}>
                🎱 View numbers{round.winning_numbers ? ' & results' : ''}
              </button>
            )}
            {round.has_ticket_image && (
              <button onClick={() => setShowPhoto(true)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: 'var(--tg)', fontSize: 13, fontWeight: 600,
                }}>
                📎 View ticket photo
              </button>
            )}
            {(round.my_shares > 0 || round.my_stake) && (
              <button onClick={() => downloadGroupPlayForm(round.id)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: 'var(--tg)', fontSize: 13, fontWeight: 600,
                }}>
                📄 Group play form
              </button>
            )}
          </div>
        </>
      )}

      {showPhoto && <TicketPhotoModal round={round} onClose={() => setShowPhoto(false)} />}
      {showNumbers && <TicketNumbersModal round={round} onClose={() => setShowNumbers(false)} />}
      {showPool && <ParticipantsModal round={round} onClose={() => setShowPool(false)} />}
    </div>
  )
}

export default function Rounds() {
  const [rounds, setRounds] = useState(null)
  const [filter, setFilter] = useState('All')

  useEffect(() => {
    api.rounds.list().then(d => setRounds(d.rounds || [])).catch(() => setRounds([]))
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
  const totalStaked = myRounds.reduce((a, r) => a + (r.my_stake || 0), 0)
  const net = totalWon - totalStaked

  const filtered = rounds.filter(r => {
    const ds = r.display_status || r.status
    if (filter === 'All')   return true
    if (filter === 'Live')     return ['RALLY','LOCKED','OPEN','CLOSING','UPLOADED','live','open','uploaded','closed'].includes(ds)
    if (filter === 'Drawn') return ds === 'REVEALED'
    if (filter === 'Won')   return ds === 'WON'
    return true
  })

  return (
    <div className="tab-content">
      <div style={{ padding: '10px 16px 6px' }}>
        <div className="card" style={{ background: 'linear-gradient(135deg, #1f2c3a, #1a2531)' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <div className="col gap-4">
              <span style={{ fontSize: 12, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Played</span>
              <span className="mono" style={{ fontSize: 21, fontWeight: 700 }}>{myRounds.length}</span>
              <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>rounds joined</span>
            </div>
            <div className="col gap-4" style={{ borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Won</span>
              <span className="mono" style={{ fontSize: 21, fontWeight: 700, color: 'var(--money)' }}>{fmtCAD(totalWon)}</span>
              <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>in prizes</span>
            </div>
            <div className="col gap-4" style={{ borderLeft: '.5px solid var(--hairline-2)', paddingLeft: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--tx-2)', letterSpacing: '.4px', textTransform: 'uppercase' }}>Net</span>
              <span className="mono" style={{ fontSize: 21, fontWeight: 700, color: net >= 0 ? 'var(--money)' : 'var(--danger)' }}>
                {net >= 0 ? '+' : ''}{fmtCAD(net)}
              </span>
              <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>{fmtCAD(totalStaked)} staked</span>
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
