import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { StatusPill } from '../components/StatusPill.jsx'
import { UsersIcon, WalletIcon, TicketIcon, TrophyIcon, ShieldIcon, CheckIcon, XIcon } from '../components/Icon.jsx'

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s.includes('T') ? s : s + 'T00:00:00')
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

const TODAY = new Date().toISOString().slice(0, 10)

export default function Admin() {
  const [tab,        setTab]        = useState('round')
  const [round,      setRound]      = useState(undefined)
  const [deposits,   setDeposits]   = useState(null)
  const [members,    setMembers]    = useState(null)
  const [busy,       setBusy]       = useState({})
  const [drawResult, setDrawResult] = useState(null)
  const [showNew,    setShowNew]    = useState(false)
  const [newDate,    setNewDate]    = useState('')
  const [showToast,  toastNode]     = useToast()

  const loadRound    = useCallback(() => api.admin.round().then(d => setRound(d.round)).catch(() => setRound(null)), [])
  const loadDeposits = useCallback(() => api.admin.deposits().then(d => setDeposits(d.deposits)).catch(() => setDeposits([])), [])
  const loadMembers  = useCallback(() => api.admin.members().then(d => setMembers(d.members)).catch(() => setMembers([])), [])

  useEffect(() => { loadRound(); loadDeposits(); loadMembers() }, [])

  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  async function openRound() {
    setB('new', true)
    try {
      const res = await api.admin.newRound(newDate || undefined)
      showToast(`Round #${res.round_id} opened!`)
      await loadRound()
      setShowNew(false); setNewDate('')
    } catch (err) { showToast(err.message, true) }
    finally { setB('new', false) }
  }

  async function roundAction(key, fn, label) {
    setB(key, true)
    try {
      const res = await fn()
      showToast(label(res))
      await loadRound()
      if (key === 'draw') setDrawResult(res)
    } catch (err) { showToast(err.message, true) }
    finally { setB(key, false) }
  }

  async function resolveDeposit(id, action) {
    setB(`d${id}`, true)
    try {
      await api.admin.resolve(id, action)
      showToast(action === 'approve' ? 'Deposit approved!' : 'Deposit rejected.')
      await loadDeposits()
    } catch (err) { showToast(err.message, true) }
    finally { setB(`d${id}`, false) }
  }

  function confirmDraw() {
    const run = () => roundAction('draw', api.admin.draw,
      r => `Winner: ${r.winner_name} — ${fmtCAD(r.pool)}`)
    const tg = window.Telegram?.WebApp
    if (tg?.showConfirm) tg.showConfirm('Draw a winner now? This cannot be undone.', ok => { if (ok) run() })
    else if (window.confirm('Draw a winner now? This cannot be undone.')) run()
  }

  const ds      = round?.display_status
  const st      = round?.status
  const canOpen = !round || ds === 'done'
  const canClose = st === 'open'
  const canDraw  = st === 'closed'

  const pendingCount = deposits ? deposits.filter(d => d.status === 'pending').length : 0

  return (
    <div className="tab-content">
      {toastNode}

      {/* Metric strip */}
      <div style={{ padding: '10px 16px 0', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        {[
          { Icon: UsersIcon,  label: 'Members',  value: members?.length ?? '—',            color: 'var(--tg)'    },
          { Icon: WalletIcon, label: 'Pending',  value: pendingCount || '—',               color: 'var(--warn)'  },
          { Icon: TicketIcon, label: 'Pool',     value: round ? fmtCAD(round.pool) : '—',  color: 'var(--money)' },
        ].map(({ Icon, label, value, color }) => (
          <div key={label} className="card col gap-4" style={{ padding: '10px 12px' }}>
            <Icon width={14} height={14} style={{ color }} />
            <span className="mono" style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
            <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Tab pills */}
      <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8 }}>
        {[
          { id: 'round',    label: 'Round'   },
          { id: 'deposits', label: pendingCount ? `Deposits (${pendingCount})` : 'Deposits' },
          { id: 'members',  label: 'Members' },
        ].map(t => (
          <button key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              flex: 1, padding: '7px 0', borderRadius: 10, border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: 600,
              background: tab === t.id ? 'var(--tg)' : 'var(--surface-2)',
              color: tab === t.id ? '#fff' : 'var(--tx-2)',
            }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Round tab ── */}
      {tab === 'round' && (
        <div style={{ padding: '12px 16px 24px' }}>
          {round === undefined ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}><div className="spinner" /></div>
          ) : round ? (
            <>
              <div className="card" style={{ marginBottom: 12 }}>
                <div className="row between" style={{ marginBottom: 12 }}>
                  <span style={{ fontSize: 15, fontWeight: 700 }}>Round #{round.id}</span>
                  <StatusPill status={ds} />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                  {[
                    ['Pool',         fmtCAD(round.pool)],
                    ['Participants', round.participants.length],
                    ['Draw date',    round.draw_date ? fmtDate(round.draw_date) : '—'],
                    ['Status',       ds || st],
                  ].map(([k, v]) => (
                    <div key={k} className="col gap-4">
                      <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{k}</span>
                      <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{v}</span>
                    </div>
                  ))}
                </div>

                {round.participants.length > 0 && (
                  <>
                    <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                    {round.participants.map(p => (
                      <div key={p.user_id} style={{ marginBottom: 10 }}>
                        <div className="row between">
                          <span style={{ fontSize: 13, fontWeight: 500 }}>
                            {p.won ? '🏆 ' : ''}{p.full_name}
                          </span>
                          <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
                            {p.pct}% · {fmtCAD(p.amount)}
                          </span>
                        </div>
                        <div className="bar" style={{ marginTop: 4 }}>
                          <span style={{ width: `${p.pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </div>

              {drawResult && (
                <div className="card" style={{ marginBottom: 12, borderColor: 'rgba(245,199,59,.3)', textAlign: 'center' }}>
                  <div style={{ fontSize: 28, marginBottom: 6 }}>🏆</div>
                  <div style={{ fontWeight: 700, fontSize: 18 }}>{drawResult.winner_name}</div>
                  <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 4 }}>
                    Prize: {fmtCAD(drawResult.pool)} · {drawResult.winner_pct}% chance
                  </div>
                </div>
              )}
            </>
          ) : null}

          {/* Actions */}
          <div className="col" style={{ gap: 8 }}>
            <button className="btn btn-primary btn-block"
              disabled={!canOpen || busy.new}
              onClick={() => setShowNew(true)}
              style={{ opacity: canOpen ? 1 : .4 }}>
              Open New Round
            </button>
            <button className="btn btn-block"
              style={{ background: 'var(--surface-2)', opacity: canClose ? 1 : .4 }}
              disabled={!canClose || busy.close}
              onClick={() => roundAction('close', api.admin.closeRound, r => `Round #${r.round_id} closed.`)}>
              {busy.close ? 'Closing…' : 'Close Round'}
            </button>
            <button className="btn btn-block"
              style={{ background: canDraw ? 'rgba(242,163,59,.15)' : 'var(--surface-2)', color: canDraw ? 'var(--warn)' : undefined, opacity: canDraw ? 1 : .4 }}
              disabled={!canDraw || busy.draw}
              onClick={confirmDraw}>
              {busy.draw ? 'Drawing…' : '🎲 Draw Winner'}
            </button>
          </div>
        </div>
      )}

      {/* ── Deposits tab ── */}
      {tab === 'deposits' && (
        <div style={{ padding: '12px 16px 24px' }}>
          {!deposits ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}><div className="spinner" /></div>
          ) : deposits.length === 0 ? (
            <div className="empty" style={{ paddingTop: 40 }}>
              <span style={{ fontSize: 36 }}>✅</span>
              <span className="e-sub">No pending deposits</span>
            </div>
          ) : deposits.map(d => (
            <div key={d.id} className="card" style={{ marginBottom: 10 }}>
              <div className="row between" style={{ marginBottom: 10 }}>
                <div className="row gap-10">
                  <div style={{
                    width: 36, height: 36, borderRadius: 50,
                    background: 'var(--surface-2)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                    fontSize: 14, fontWeight: 700, color: 'var(--tg)',
                    flexShrink: 0,
                  }}>
                    {(d.full_name || '?')[0].toUpperCase()}
                  </div>
                  <div className="col gap-4">
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{d.full_name}</span>
                    {d.username && <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>@{d.username}</span>}
                  </div>
                </div>
                <div className="col" style={{ textAlign: 'right', gap: 2 }}>
                  <span className="mono" style={{ fontSize: 18, fontWeight: 700, color: 'var(--money)' }}>
                    {fmtCAD(d.amount)}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--tx-3)' }}>{d.created_at?.slice(0, 10)}</span>
                </div>
              </div>
              <div className="row gap-8">
                <button className="btn btn-block"
                  style={{ flex: 1, background: 'rgba(78,208,122,.12)', color: 'var(--money)', border: 'none' }}
                  disabled={busy[`d${d.id}`]}
                  onClick={() => resolveDeposit(d.id, 'approve')}>
                  <CheckIcon width={14} height={14} /> Approve
                </button>
                <button className="btn btn-block"
                  style={{ flex: 1, background: 'rgba(242,92,92,.12)', color: 'var(--danger)', border: 'none' }}
                  disabled={busy[`d${d.id}`]}
                  onClick={() => resolveDeposit(d.id, 'reject')}>
                  <XIcon width={14} height={14} /> Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Members tab ── */}
      {tab === 'members' && (
        <div style={{ padding: '12px 16px 24px' }}>
          {!members ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}><div className="spinner" /></div>
          ) : (
            <div className="card" style={{ padding: 0 }}>
              {members.map((m, idx) => (
                <div key={m.telegram_id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '12px 14px',
                    borderBottom: idx < members.length - 1 ? '.5px solid var(--hairline)' : 'none',
                  }}>
                  <div style={{
                    width: 36, height: 36, borderRadius: 50, flexShrink: 0,
                    background: m.is_trustee ? 'rgba(245,199,59,.14)' : 'var(--surface-2)',
                    color: m.is_trustee ? 'var(--gold)' : 'var(--tx-2)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 14, fontWeight: 700,
                  }}>
                    {m.is_trustee ? <ShieldIcon width={16} height={16} /> : (m.full_name || '?')[0].toUpperCase()}
                  </div>
                  <div className="col grow gap-4" style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 500, fontSize: 14 }}>
                      {m.full_name}
                      {m.is_trustee && <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--gold)', fontWeight: 700 }}>TRUSTEE</span>}
                    </span>
                    {m.username && <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>@{m.username}</span>}
                  </div>
                  <div className="col" style={{ textAlign: 'right', gap: 2, flexShrink: 0 }}>
                    <span className="mono" style={{ fontSize: 14, fontWeight: 700 }}>{fmtCAD(m.credit)}</span>
                    <span style={{ fontSize: 10, color: 'var(--tx-3)' }}>balance</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* New round sheet */}
      {showNew && (
        <div className="sheet-overlay" onClick={() => setShowNew(false)}>
          <div className="sheet" onClick={e => e.stopPropagation()}>
            <div className="handle" />
            <div className="sheet-head">
              <span className="sheet-title">Open New Round</span>
              <button className="sheet-close" onClick={() => setShowNew(false)}>✕</button>
            </div>
            <div className="body">
              <p style={{ fontSize: 13, color: 'var(--tx-2)', marginBottom: 16 }}>
                Set a draw date so participants know when this round closes.
              </p>
              <div className="col gap-4" style={{ marginBottom: 16 }}>
                <span style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px' }}>
                  DRAW DATE (OPTIONAL)
                </span>
                <input className="input" type="date" min={TODAY} value={newDate}
                  onChange={e => setNewDate(e.target.value)} />
              </div>
              <button className="btn btn-primary btn-block" disabled={busy.new} onClick={openRound}>
                {busy.new ? 'Opening…' : 'Open Round'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
