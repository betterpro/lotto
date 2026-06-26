import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { Countdown } from '../components/Countdown.jsx'
import LiveRoundDeck from '../components/LiveRoundDeck.jsx'
import { lotteryMeta, JACKPOT_PENDING_LABEL } from '../lottery.js'
import LotteryLogo from '../components/LotteryLogo.jsx'
import { WalletIcon, BoltIcon, PlusIcon, ShareIcon } from '../components/Icon.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'

function fmtCAD(n, decimals = 2) {
  return '$' + Number(n || 0).toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}
function fmtBig(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(0) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K'
  return String(n)
}
function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

function playerCount(round) {
  if (!round) return 0
  if (Array.isArray(round.participants)) return round.participants.length
  const n = round.participants_count ?? round.participants
  return typeof n === 'number' ? n : 0
}

// ─── Join sheet ──────────────────────────────────────────────────────────────
function JoinSheet({ open, onClose, round, user, onJoined, showToast }) {
  const PRICE = round?.price_per_share || 5
  const [shares, setShares] = useState(1)
  const [busy, setBusy] = useState(false)
  const cost = shares * PRICE
  const credit = user?.credit ?? 0
  const after = credit - cost
  const shortfall = Math.max(0, cost - credit)
  const insufficient = after < 0

  useEffect(() => {
    if (open) setShares(1)
  }, [open, round?.id])

  async function confirm() {
    if (insufficient) {
      showToast('Top up your balance on Home first, then join again.', 'error')
      return
    }
    setBusy(true)
    try {
      await api.participate(cost, round.id)
      onJoined(shares)
      onClose()
    } catch (e) { showToast(e.message, 'error') }
    finally { setBusy(false) }
  }

  if (!open || !round) return null
  const poolAfter = (round.pool || 0) + cost
  const myStakeAfter = (round.my_stake || 0) + cost
  const sharePct = poolAfter > 0 ? (myStakeAfter / poolAfter * 100).toFixed(1) : '0.0'

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Add shares · Round #{round.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <p style={{ fontSize: 14, color: 'var(--tx-2)', marginBottom: 12 }}>
            Each share = {fmtCAD(PRICE, 0)} in the pool
          </p>
          <div className="stepper" style={{ marginBottom: 12 }}>
            <button className="stepper-btn" onClick={() => setShares(Math.max(1, shares - 1))}>−</button>
            <div className="col" style={{ alignItems: 'center' }}>
              <span className="mono" style={{ fontSize: 40, fontWeight: 700 }}>{shares}</span>
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>shares</span>
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
              ['Cost',           fmtCAD(cost),                null],
              ['Balance before', fmtCAD(user?.credit ?? 0),  'var(--tx-2)'],
              ['Balance after',  fmtCAD(after),               after < 0 ? 'var(--danger)' : 'var(--money)'],
              ['Your pool share',`${sharePct}%`,               null],
            ].map(([k,v,c]) => (
              <div key={k} className="sum-row">
                <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>{k}</span>
                <span className="mono" style={{ fontSize: 15, fontWeight: 600, color: c || '#fff' }}>{v}</span>
              </div>
            ))}
          </div>
          {insufficient ? (
            <>
              <div className="card" style={{
                marginBottom: 12, padding: 14,
                borderColor: 'rgba(255,80,80,.35)',
                background: 'rgba(255,80,80,.08)',
              }}>
                <p style={{ margin: '0 0 6px', fontWeight: 700, fontSize: 15, color: 'var(--danger)' }}>
                  Not enough credit
                </p>
                <p style={{ margin: 0, fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.5 }}>
                  You need at least {fmtCAD(cost)} for {shares} share{shares !== 1 ? 's' : ''} ({fmtCAD(shortfall)} short).
                  Close this screen, tap your balance on Home to top up, then come back and join again.
                  Paying does not join you until you confirm here.
                </p>
              </div>
              <button className="btn btn-block" type="button" onClick={onClose}>
                Close
              </button>
            </>
          ) : (
            <button className="btn btn-primary btn-block" disabled={busy} onClick={confirm}>
              {busy ? 'Processing…' : `Confirm · ${fmtCAD(cost)}`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Groups: invite & create ─────────────────────────────────────────────────
function GroupsSections({ user, onUserUpdate, onActiveGroupChange, showToast }) {
  const groups = user.groups?.length ? user.groups : (user.group ? [{ ...user.group, is_active: true }] : [])
  const activeId = user.active_group_id ?? user.group?.id ?? groups[0]?.id
  const [inviteGroupId, setInviteGroupId] = useState(activeId)
  const [newGroupName, setNewGroupName] = useState('')
  const [newPlan, setNewPlan] = useState('subscription')
  const [applyBusy, setApplyBusy] = useState(false)
  const [trusteeApp, setTrusteeApp] = useState(null)
  const [joinCode, setJoinCode] = useState(null)

  useEffect(() => {
    setInviteGroupId(activeId)
  }, [activeId])

  useEffect(() => {
    if (!inviteGroupId) { setJoinCode(null); return }
    let cancelled = false
    api.invite(inviteGroupId)
      .then(r => { if (!cancelled) setJoinCode(r.join_code || null) })
      .catch(() => { if (!cancelled) setJoinCode(null) })
    return () => { cancelled = true }
  }, [inviteGroupId])

  async function copyCode() {
    if (!joinCode) return
    try {
      await navigator.clipboard.writeText(joinCode)
      showToast('Join code copied', 'success')
    } catch {
      showToast(`Join code: ${joinCode}`, 'success')
    }
  }

  useEffect(() => {
    if (!user.is_group_trustee) {
      api.trustee.application().then(r => setTrusteeApp(r.application)).catch(() => {})
    }
  }, [user.is_group_trustee])

  async function shareInvite() {
    const g = groups.find(x => x.id === inviteGroupId) || groups[0]
    if (!g) {
      showToast('Join a group first', 'error')
      return
    }
    try {
      const { link } = await api.invite(g.id)
      const text = `Join ${g.name} on Lotto Chee — group lottery with friends!`
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`
      if (window.Telegram?.WebApp?.openTelegramLink) {
        window.Telegram.WebApp.openTelegramLink(shareUrl)
      } else {
        await navigator.clipboard.writeText(link)
        showToast('Invite link copied', 'success')
      }
    } catch {
      showToast('Could not get invite link', 'error')
    }
  }

  async function setActiveGroup(groupId) {
    try {
      const r = await api.groups.setActive(groupId)
      onUserUpdate({ ...user, ...r })
      setInviteGroupId(groupId)
      onActiveGroupChange?.()
      showToast('Active group updated', 'success')
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  const inviteGroup = groups.find(g => g.id === inviteGroupId) || groups[0]

  return (
    <>
      <div className="section"><div className="label">Invite friends to your group</div></div>
      <div className="stack">
        <div className="card" style={{ padding: '12px 14px', marginBottom: 8 }}>
          <p style={{ fontSize: 13, color: 'var(--tx-2)', margin: '0 0 10px', lineHeight: 1.5 }}>
            Trustees and members can invite new players to a group. You can belong to several groups;
            choose which one is active for rounds and deposits.
          </p>
          {groups.length === 0 ? (
            <p style={{ fontSize: 14, color: 'var(--tx-3)', margin: 0 }}>
              Open a group invite link from your trustee to join first.
            </p>
          ) : (
            <>
              {groups.length > 1 && (
                <label className="col gap-4" style={{ marginBottom: 10, display: 'flex' }}>
                  <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase' }}>
                    Active group (rounds &amp; wallet context)
                  </span>
                  <select
                    className="input"
                    value={activeId ?? ''}
                    onChange={e => setActiveGroup(Number(e.target.value))}
                  >
                    {groups.map(g => (
                      <option key={g.id} value={g.id}>
                        {g.name}{g.is_trustee ? ' · trustee' : ''}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {groups.length > 1 && (
                <label className="col gap-4" style={{ marginBottom: 10, display: 'flex' }}>
                  <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase' }}>
                    Invite link for
                  </span>
                  <select
                    className="input"
                    value={inviteGroupId ?? ''}
                    onChange={e => setInviteGroupId(Number(e.target.value))}
                  >
                    {groups.map(g => (
                      <option key={g.id} value={g.id}>{g.name}</option>
                    ))}
                  </select>
                </label>
              )}
              {joinCode && (
                <div
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    gap: 10, padding: '10px 12px', marginBottom: 10, borderRadius: 12,
                    background: 'var(--bg-2, #f5f5f7)', border: '1px solid var(--bd, #e5e5e5)',
                  }}
                >
                  <div className="col" style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
                    <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: 1 }}>
                      Join code
                    </span>
                    <span style={{ fontSize: 23, fontWeight: 800, letterSpacing: 4, fontFamily: 'monospace' }}>
                      {joinCode}
                    </span>
                  </div>
                  <button className="btn btn-ghost btn-sm" type="button" onClick={copyCode}>
                    Copy
                  </button>
                </div>
              )}
              <p style={{ fontSize: 12, color: 'var(--tx-3)', margin: '0 0 10px', lineHeight: 1.5 }}>
                Share this code with friends — they enter it on the “Join your group” screen to join.
              </p>
              <button className="btn btn-ghost btn-block btn-sm" type="button" onClick={shareInvite}>
                <ShareIcon width={14} height={14} />
                {inviteGroup
                  ? `Invite to ${inviteGroup.name}`
                  : 'Share group invite'}
              </button>
            </>
          )}
        </div>
      </div>

      {!user.is_group_trustee && (
        <>
          <div className="section"><div className="label">Create your own group</div></div>
          <div className="stack">
            <div className="card" style={{ padding: '12px 14px', marginBottom: 8 }}>
              {trusteeApp?.status === 'pending' ? (
                <p style={{ fontSize: 14, color: 'var(--tx-2)', margin: 0 }}>
                  Your request for <strong>{trusteeApp.proposed_group_name}</strong> is pending platform approval.
                </p>
              ) : trusteeApp?.status === 'rejected' ? (
                <p style={{ fontSize: 14, color: 'var(--danger)', margin: '0 0 10px' }}>
                  Request rejected{trusteeApp.review_notes ? `: ${trusteeApp.review_notes}` : '.'}
                </p>
              ) : (
                <>
                  <p style={{ fontSize: 13, color: 'var(--tx-2)', margin: '0 0 10px', lineHeight: 1.5 }}>
                    Apply to run your own group: open rounds, approve deposits, and invite members.
                    You can still stay in other groups as a player.
                  </p>
                  <input
                    className="input"
                    placeholder="Your group name"
                    value={newGroupName}
                    onChange={e => setNewGroupName(e.target.value)}
                    style={{ marginBottom: 10 }}
                  />
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    {[
                      { id: 'subscription', t: 'Subscription', s: '$6.99/mo · no prize cut' },
                      { id: 'prize_share', t: 'Big-prize share', s: 'Free · 5% of wins over $1,000' },
                    ].map(o => {
                      const on = newPlan === o.id
                      return (
                        <button type="button" key={o.id} onClick={() => setNewPlan(o.id)}
                          style={{ flex: 1, textAlign: 'left', padding: '9px 11px', borderRadius: 11, cursor: 'pointer',
                            background: on ? 'rgba(46,166,255,.12)' : 'var(--bg-3)',
                            border: `1.5px solid ${on ? 'var(--tg)' : 'var(--hairline-2, #34465A)'}` }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: on ? 'var(--tg)' : 'var(--tx-1)' }}>{o.t}</div>
                          <div style={{ fontSize: 10, color: 'var(--tx-2)', marginTop: 2, lineHeight: 1.3 }}>{o.s}</div>
                        </button>
                      )
                    })}
                  </div>
                  <p style={{ fontSize: 10, color: 'var(--tx-3)', margin: '0 0 10px', lineHeight: 1.4 }}>
                    Plan is locked into the group agreement and can’t be changed later.
                  </p>
                  <button
                    className="btn btn-primary btn-sm btn-block"
                    type="button"
                    disabled={applyBusy || !newGroupName.trim()}
                    onClick={async () => {
                      setApplyBusy(true)
                      try {
                        await api.trustee.apply(newGroupName.trim(), newPlan)
                        const r = await api.trustee.application()
                        setTrusteeApp(r.application)
                        setNewGroupName('')
                        showToast('Application submitted', 'success')
                      } catch (e) {
                        showToast(e.message, 'error')
                      } finally {
                        setApplyBusy(false)
                      }
                    }}
                  >
                    {applyBusy ? 'Submitting…' : 'Request new group'}
                  </button>
                </>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}

// ─── Live round card ─────────────────────────────────────────────────────────
function LiveRoundCard({ round, onJoin, peek }) {
  const ds = round.display_status
  const isRally   = ['RALLY', 'OPEN'].includes(ds)
  const isLocked  = ds === 'LOCKED'
  const isDrawn   = ds === 'REVEALED'
  const isLive    = isRally || isLocked || isDrawn
  const jackpot   = round.jackpot || 0
  const hasTarget   = (round.tickets_target || 0) > 0
  const poolTarget  = hasTarget ? round.tickets_target * (round.price_per_share || 5) : 0
  const poolRaised  = round.pool || 0
  const poolPct     = poolTarget > 0 ? Math.min(1, poolRaised / poolTarget) : 0
  const lotto       = lotteryMeta(round.lottery_type)

  return (
    <div className="jackpot" style={peek ? { pointerEvents: 'none' } : undefined}>
      <div className="row between" style={{ marginBottom: 14 }}>
        <div className="row gap-8">
          <span className="status-dot live" />
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.8px', color: 'var(--money)' }}>
            {isLocked ? 'WAITING FOR DRAW' : isDrawn ? 'DRAWN' : isRally ? 'OPEN' : 'LIVE ROUND'}
          </span>
        </div>
        <span className="mono dim" style={{ fontSize: 13 }}>#{round.group_seq ?? round.id}</span>
      </div>

      <div className="row gap-10" style={{ alignItems: 'center' }}>
        <LotteryLogo type={round.lottery_type} height={44} style={{ width: 56, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, color: 'var(--tx-2)', marginBottom: 2, letterSpacing: '.3px' }}>
            Estimated jackpot
          </div>
          {jackpot > 0 ? (
            <div className="pool-display">
              <span className="cur">$</span>
              <span className="amt">{fmtBig(jackpot)}</span>
              <span className="unit">CAD</span>
            </div>
          ) : (
            <div style={{
              fontSize: 16, fontWeight: 500, color: 'var(--tx-3)', fontStyle: 'italic',
              lineHeight: 1.35, paddingTop: 2,
            }}>
              {JACKPOT_PENDING_LABEL}
            </div>
          )}
        </div>
      </div>

      {round.draw_date && (
        <div style={{ margin: '18px 0 14px' }}>
          <Countdown to={round.draw_date + (round.draw_date.includes('T') ? '' : 'T22:30:00')} />
          <div className="row between" style={{ marginTop: 6, fontSize: 12, color: 'var(--tx-3)', whiteSpace: 'nowrap' }}>
            <span>Draw date</span>
            <span>{round.draw_date}</span>
          </div>
        </div>
      )}

      <div className="row between" style={{ marginBottom: 6, marginTop: 14 }}>
        <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
          {hasTarget ? `Pool · ${round.tickets_target} tickets target` : 'Pool raised'}
        </span>
        <span className="mono" style={{ fontSize: 13 }}>
          <span style={{ color: 'var(--money)' }}>{fmtCAD(poolRaised, 0)}</span>
          {hasTarget && <span style={{ color: 'var(--tx-3)' }}> / {fmtCAD(poolTarget, 0)}</span>}
        </span>
      </div>
      {hasTarget && <div className="bar"><span style={{ width: (poolPct * 100) + '%' }} /></div>}

      <div className="row between" style={{ marginTop: 14 }}>
        <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
          {playerCount(round)} player{playerCount(round) !== 1 ? 's' : ''} in pool
        </span>
        {round.my_pct != null && (
          <span className="chip chip-gold">
            <BoltIcon width={11} height={11} />{round.my_pct}% share
          </span>
        )}
      </div>

      {!peek && isLive && (
        round.entries_open !== false ? (
          <button className="btn btn-primary btn-block" style={{ marginTop: 16 }} onClick={onJoin}>
            <PlusIcon width={16} height={16} />
            {round.my_stake ? `Add more shares · $${round.price_per_share || 5} each` : `Join · $${round.price_per_share || 5} per share`}
          </button>
        ) : (
          <p style={{ marginTop: 14, fontSize: 13, color: 'var(--tx-3)', textAlign: 'center', lineHeight: 1.5 }}>
            Entries closed — trustee is buying tickets. Your draw agreement is in Rounds.
          </p>
        )
      )}
    </div>
  )
}

// ─── Home screen ─────────────────────────────────────────────────────────────
export default function Home({ user, onUserUpdate }) {
  const [liveRounds, setLiveRounds] = useState(undefined)
  const [roundIndex, setRoundIndex] = useState(0)
  const [lastDrawn, setLastDrawn] = useState(null)
  const [sub, setSub]       = useState(null)
  const [join, setJoin]             = useState(false)
  const showToast = useToast()
  const navigate = useNavigate()

  const round = liveRounds?.[roundIndex] ?? null

  // Active group name for the Status tile (mirrors GroupsSections' derivation).
  const _groups = user.groups?.length ? user.groups : (user.group ? [user.group] : [])
  const _activeId = user.active_group_id ?? user.group?.id ?? _groups[0]?.id
  const activeGroupName = (_groups.find(g => g.id === _activeId) || _groups[0])?.name || 'No group yet'

  function reloadLive() {
    return api.rounds.open().then(d => {
      const list = d.rounds || []
      setLiveRounds(list)
      setRoundIndex(i => Math.min(i, Math.max(0, list.length - 1)))
    }).catch(() => setLiveRounds([]))
  }

  useEffect(() => {
    reloadLive()
    api.rounds.list().then(d => {
      const drawn = (d.rounds || []).find(r =>
        ['REVEALED', 'WON', 'LOST', 'DRAWN'].includes(r.display_status))
      setLastDrawn(drawn || null)
    }).catch(() => {})
    api.stripe.subscription().then(r => setSub(r.subscription)).catch(() => {})
  }, [])

  const myShares  = round?.my_stake ? Math.round(round.my_stake / (round.price_per_share || 5)) : 0
  const poolRaised = round?.pool || 0
  const jackpot    = round?.jackpot || 0
  const winPot     = jackpot && poolRaised > 0 && round?.my_stake
    ? Math.round((round.my_stake / poolRaised) * jackpot)
    : null

  const trusteeName = user.trustee?.full_name || user.trustee?.username
  const groupName = user.group?.name

  return (
    <div className="tab-content">
      {trusteeName && (
        <div style={{
          margin: '8px 16px 0', padding: '12px 14px', borderRadius: 12,
          background: 'linear-gradient(135deg, rgba(245,199,59,.12), rgba(46,166,255,.08))',
          border: '.5px solid var(--hairline-2)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <TelegramAvatar user={user.trustee} size={44} />
          <div className="col gap-2 grow" style={{ minWidth: 0 }}>
            <span style={{ fontSize: 12, color: 'var(--tx-2)', textTransform: 'uppercase', letterSpacing: '.4px' }}>
              Your trustee
            </span>
            <span style={{ fontSize: 18, fontWeight: 800, lineHeight: 1.2 }}>{trusteeName}</span>
            {groupName && (
              <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>{groupName}</span>
            )}
          </div>
        </div>
      )}

      {/* Greeting + balance */}
      <div style={{ padding: '12px 16px 8px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <TelegramAvatar user={user} size={40} />
        <div className="col grow gap-4">
          <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>Welcome back</span>
          <span style={{ fontSize: 16, fontWeight: 600 }}>{user.full_name || user.username || 'Player'}</span>
        </div>
        <div className="chip chip-money" onClick={() => navigate('/topup')} style={{ cursor: 'pointer', gap: 6 }}>
          <WalletIcon width={13} height={13} />
          <span className="mono">{fmtCAD(user.credit ?? 0)}</span>
        </div>
      </div>

      {/* Live rounds — swipe deck */}
      {liveRounds === undefined ? (
        <div style={{ padding: '40px 0', display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
      ) : liveRounds.length === 0 ? (
        <div style={{ padding: '8px 16px' }}>
          <div className="jackpot" style={{ textAlign: 'center', padding: '40px 18px' }}>
            <div style={{ fontSize: 40, marginBottom: 10 }}>🎰</div>
            <p style={{ fontWeight: 600, marginBottom: 4 }}>No active round</p>
            <p style={{ fontSize: 14, color: 'var(--tx-2)' }}>The trustee will open one soon!</p>
          </div>
        </div>
      ) : (
        <LiveRoundDeck
          rounds={liveRounds}
          index={roundIndex}
          onIndexChange={setRoundIndex}
          renderCard={(r, peek) => (
            <LiveRoundCard round={r} peek={peek} onJoin={() => setJoin(true)} />
          )}
        />
      )}

      {/* Your stake */}
      {round?.my_stake != null && (
        <>
          <div className="section"><div className="label">Your stake in Round #{round.id}</div></div>
          <div className="stack">
            <div className="card">
              <div className="row between">
                <div className="col gap-4">
                  <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Shares owned</span>
                  <div className="row gap-8" style={{ alignItems: 'baseline' }}>
                    <span className="mono" style={{ fontSize: 27, fontWeight: 700 }}>{myShares}</span>
                    <span style={{ fontSize: 14, color: 'var(--tx-3)' }}>
                      share{myShares !== 1 ? 's' : ''} · {playerCount(round)} players
                    </span>
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--money)' }}>
                    = {fmtCAD(round.my_stake)} invested
                  </span>
                </div>
                <div className="col gap-4" style={{ alignItems: 'flex-end' }}>
                  <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
                    {winPot ? 'Win potential' : 'Win chance'}
                  </span>
                  {winPot ? (
                    <>
                      <span className="mono" style={{ fontSize: 27, fontWeight: 700, color: 'var(--gold)' }}>
                        ${fmtBig(winPot)}
                      </span>
                      <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>if 1 ticket wins jackpot</span>
                    </>
                  ) : (
                    <span className="mono" style={{ fontSize: 27, fontWeight: 700, color: 'var(--gold)' }}>
                      {round.my_pct}%
                    </span>
                  )}
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
          <span className="v">{fmtCAD(user.credit ?? 0)}</span>
          <span className="delta" style={{ color: 'var(--tg)', cursor: 'pointer' }}
            onClick={() => navigate('/topup')}>Tap to top up →</span>
        </div>
        <div className="stat">
          <span className="k">Status</span>
          <span className="v" style={{ fontSize: 17 }}>{user.is_group_trustee ? 'Trustee' : 'Member'}</span>
          <span className="delta">{activeGroupName}</span>
        </div>
        {sub && (
          <div className="stat" style={{ gridColumn: 'span 2' }}>
            <span className="k">Monthly plan</span>
            <span className="v" style={{ color: 'var(--money)', fontSize: 19 }}>${sub.amount}/mo</span>
            {sub.next_billing && <span className="delta">Next charge: {sub.next_billing}</span>}
          </div>
        )}
      </div>

      <GroupsSections
        user={user}
        onUserUpdate={onUserUpdate}
        onActiveGroupChange={reloadLive}
        showToast={showToast}
      />

      {/* Last drawn round result */}
      {lastDrawn && (
        <>
          <div className="section">
            <div className="row between">
              <div className="label" style={{ marginBottom: 0 }}>Last round</div>
            </div>
          </div>
          <div className="stack" style={{ marginBottom: 12 }}>
            <div className="card">
              <div className="row between" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>
                  Round #{lastDrawn.id}{lastDrawn.draw_date ? ` · ${lastDrawn.draw_date}` : ''}
                </span>
                <span className={`status-pill ${lastDrawn.display_status === 'WON' ? 'won' : 'revealed'}`}>
                  {lastDrawn.display_status === 'WON' ? 'Won' : 'Drawn'}
                </span>
              </div>
              <div className="row between">
                {lastDrawn.my_prize > 0 ? (
                  <span className="chip chip-money">Won {fmtCAD(lastDrawn.my_prize)}</span>
                ) : lastDrawn.my_stake ? (
                  <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>No prize this round</span>
                ) : (
                  <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>Did not join</span>
                )}
                {lastDrawn.jackpot > 0 && (
                  <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
                    ${fmtBig(lastDrawn.jackpot)} jackpot
                  </span>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <JoinSheet
        open={join}
        onClose={() => setJoin(false)}
        round={round}
        user={user}
        showToast={showToast}
        onJoined={(n) => {
          showToast(`Joined with ${n} share${n > 1 ? 's' : ''}!`, 'success')
          reloadLive()
          api.me().then(onUserUpdate)
        }}
      />
    </div>
  )
}
