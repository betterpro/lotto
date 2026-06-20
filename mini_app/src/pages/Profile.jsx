import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { BellIcon, PersonIcon, TicketIcon } from '../components/Icon.jsx'
import { AgreementLink } from '../components/AgreementSheet.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'
import { LOTTERY_PREFS } from '../lottery.js'

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function getInitials(name) {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

// ── Toggle switch ─────────────────────────────────────────────────────────────
function Toggle({ on, onChange }) {
  return (
    <button onClick={() => onChange(!on)} style={{
      width: 48, height: 28, borderRadius: 14, border: 'none', cursor: 'pointer',
      background: on ? 'var(--tg)' : 'var(--bg-3)',
      position: 'relative', transition: 'background .2s', flexShrink: 0,
      boxShadow: on ? '0 0 0 1px rgba(46,166,255,.4)' : '0 0 0 1px var(--hairline-2)',
    }}>
      <span style={{
        position: 'absolute', top: 3, left: on ? 23 : 3,
        width: 22, height: 22, borderRadius: '50%',
        background: '#fff', transition: 'left .2s',
        boxShadow: '0 1px 4px rgba(0,0,0,.3)',
      }} />
    </button>
  )
}

// ── Stepper ────────────────────────────────────────────────────────────────────
function Stepper({ value, onChange, min = 1, max = 20 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <button onClick={() => onChange(Math.max(min, value - 1))}
        style={{
          width: 36, height: 36, borderRadius: 10, border: 'none',
          background: 'var(--bg-3)', color: 'var(--tx-1)', fontSize: 20,
          fontWeight: 700, cursor: 'pointer', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>−</button>
      <span className="mono" style={{ fontSize: 18, fontWeight: 700, minWidth: 28, textAlign: 'center' }}>
        {value}
      </span>
      <button onClick={() => onChange(Math.min(max, value + 1))}
        style={{
          width: 36, height: 36, borderRadius: 10, border: 'none',
          background: 'var(--bg-3)', color: 'var(--tx-1)', fontSize: 20,
          fontWeight: 700, cursor: 'pointer', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>+</button>
    </div>
  )
}

// ── Section header ─────────────────────────────────────────────────────────────
function SectionHead({ icon: Icon, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '20px 0 10px' }}>
      <div style={{
        width: 28, height: 28, borderRadius: 8,
        background: 'rgba(46,166,255,.12)', color: 'var(--tg)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon width={15} height={15} />
      </div>
      <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: '.5px',
                     textTransform: 'uppercase', color: 'var(--tx-2)' }}>
        {label}
      </span>
    </div>
  )
}

// ── Pref row ──────────────────────────────────────────────────────────────────
function PrefRow({ label, sub, right }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '11px 14px', borderBottom: '.5px solid var(--hairline)',
    }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <span style={{ fontSize: 14, fontWeight: 500 }}>{label}</span>
        {sub && <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>{sub}</span>}
      </div>
      {right}
    </div>
  )
}

const DAYS = [
  { v: null, label: 'Any'  },
  { v: 1,    label: 'Tue'  },
  { v: 4,    label: 'Fri'  },
]

const DEFAULTS = {
  auto_participate: false, shares_per_round: 1,
  max_rounds_per_month: 4, preferred_day: null,
  lottery_preference: 'both',
  notif_new_round: true, notif_reminder: true,
  notif_ticket: true, notif_results: true,
  notif_contribution: true, notif_round_closed: true,
}

export default function Profile({ user, onUserUpdate }) {
  const showToast = useToast()
  const [settings, setSettings] = useState(null)
  const [saved,    setSaved]    = useState(false)
  const [busy,     setBusy]     = useState(false)
  const [email,    setEmail]    = useState(user?.email ?? '')
  const [trusteeApp, setTrusteeApp] = useState(null)
  const [groupName, setGroupName] = useState('')
  const [applyBusy, setApplyBusy] = useState(false)

  useEffect(() => {
    api.settings.get()
      .then(s => setSettings(s))
      .catch(() => setSettings({ ...DEFAULTS }))
    if (!user?.is_group_trustee) {
      api.trustee.application().then(r => setTrusteeApp(r.application)).catch(() => {})
    }
  }, [user?.is_group_trustee])

  useEffect(() => {
    setEmail(user?.email ?? '')
  }, [user?.email])

  const set = useCallback((key, val) =>
    setSettings(prev => ({ ...prev, [key]: val })), [])

  async function save() {
    setBusy(true)
    try {
      const profile = await api.profile.updateEmail(email)
      await api.settings.put(settings)
      if (profile?.user) {
        onUserUpdate(prev => ({ ...prev, ...profile.user }))
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      showToast(e.message || 'Save failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  const photoUrl  = user?.photo_url
  const name      = user?.full_name || user?.first_name || 'You'
  const username  = user?.username
  const balance   = user?.credit ?? user?.balance ?? 0
  const sharePrice = LOTTERY_PREFS.find(p => p.v === settings?.lottery_preference)?.price ?? 9

  return (
    <div className="tab-content" style={{ paddingBottom: 32 }}>

      {/* ── Avatar + identity ── */}
      <div style={{ padding: '20px 16px 4px', display: 'flex', alignItems: 'center', gap: 16 }}>
        <TelegramAvatar user={user} size={72} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontSize: 20, fontWeight: 700 }}>{name}</span>
          {username && (
            <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>@{username}</span>
          )}
          <span className="mono" style={{
            marginTop: 4, fontSize: 18, fontWeight: 700, color: 'var(--money)',
          }}>
            {fmtCAD(balance)}
          </span>
        </div>
      </div>

      <div style={{ padding: '0 16px' }}>

        {settings === null ? (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
            <div className="spinner" />
          </div>
        ) : (
          <>
            {/* ── Contact ── */}
            <SectionHead icon={PersonIcon} label="Contact" />
            <div className="card" style={{ padding: '12px 14px', marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>E-transfer email</div>
              <p style={{ fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5, margin: '0 0 10px' }}>
                Use the same email address that appears as the sender on your Interac e-Transfer.
              </p>
              <input className="input mono" type="email" value={email}
                onChange={e => setEmail(e.target.value.trim().toLowerCase())}
                placeholder="you@example.com" />
            </div>

            {/* ── Round participation ── */}
            <SectionHead icon={TicketIcon} label="Round participation" />

            {/* Mode selector */}
            <div style={{
              background: 'var(--surface)', border: '.5px solid var(--hairline-2)',
              borderRadius: 14, overflow: 'hidden', marginBottom: 0,
            }}>
              <div style={{ padding: '10px 14px 6px' }}>
                <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.4px',
                               textTransform: 'uppercase', color: 'var(--tx-3)' }}>
                  Participation mode
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, padding: '0 14px 14px' }}>
                {[
                  { v: true,  label: '⚡ Auto',   sub: 'Join rounds automatically' },
                  { v: false, label: '✋ Manual', sub: 'Decide each round yourself' },
                ].map(opt => (
                  <button key={String(opt.v)} onClick={() => set('auto_participate', opt.v)}
                    style={{
                      padding: '10px 12px', borderRadius: 10, cursor: 'pointer',
                      textAlign: 'left', border: 'none',
                      background: settings.auto_participate === opt.v
                        ? (opt.v ? 'rgba(46,166,255,.18)' : 'rgba(78,208,122,.12)')
                        : 'var(--bg-3)',
                      outline: settings.auto_participate === opt.v
                        ? `1.5px solid ${opt.v ? 'rgba(46,166,255,.5)' : 'rgba(78,208,122,.4)'}`
                        : '1.5px solid transparent',
                    }}>
                    <div style={{ fontSize: 13, fontWeight: 700,
                                  color: settings.auto_participate === opt.v
                                    ? (opt.v ? 'var(--tg)' : 'var(--money)') : 'var(--tx-1)' }}>
                      {opt.label}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--tx-3)', marginTop: 2 }}>{opt.sub}</div>
                  </button>
                ))}
              </div>

              {settings.auto_participate && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '0 14px' }} />

                  {/* Lottery type preference */}
                  <div style={{ padding: '11px 14px 14px' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.4px',
                                  textTransform: 'uppercase', color: 'var(--tx-3)', marginBottom: 8 }}>
                      Lottery type
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                      {LOTTERY_PREFS.map(lp => (
                        <button key={lp.v} onClick={() => set('lottery_preference', lp.v)}
                          style={{
                            padding: '8px 4px', borderRadius: 10, border: 'none', cursor: 'pointer',
                            textAlign: 'center',
                            background: settings.lottery_preference === lp.v
                              ? 'rgba(46,166,255,.18)' : 'var(--bg-3)',
                            outline: settings.lottery_preference === lp.v
                              ? '1.5px solid rgba(46,166,255,.5)' : '1.5px solid transparent',
                          }}>
                          <div style={{ fontSize: 13, fontWeight: 700,
                            color: settings.lottery_preference === lp.v ? 'var(--tg)' : 'var(--tx-1)' }}>
                            {lp.label}
                          </div>
                          <div style={{ fontSize: 10, color: 'var(--tx-3)', marginTop: 2 }}>{lp.tag}</div>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '0 14px' }} />
                  <PrefRow
                    label="Shares per round"
                    sub={`${fmtCAD(settings.shares_per_round * sharePrice)} per draw`}
                    right={
                      <Stepper value={settings.shares_per_round} min={1} max={10}
                        onChange={v => set('shares_per_round', v)} />
                    }
                  />
                  <PrefRow
                    label="Max rounds/month"
                    sub="Monthly entry cap"
                    right={
                      <Stepper value={settings.max_rounds_per_month} min={1} max={8}
                        onChange={v => set('max_rounds_per_month', v)} />
                    }
                  />
                  <div style={{ padding: '11px 14px 14px', borderTop: '.5px solid var(--hairline)' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.4px',
                                  textTransform: 'uppercase', color: 'var(--tx-3)', marginBottom: 8 }}>
                      Preferred draw day
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {DAYS.map(d => (
                        <button key={String(d.v)} onClick={() => set('preferred_day', d.v)}
                          style={{
                            padding: '7px 16px', borderRadius: 20, border: 'none', cursor: 'pointer',
                            fontSize: 13, fontWeight: 600,
                            background: settings.preferred_day === d.v ? 'var(--tg)' : 'var(--bg-3)',
                            color: settings.preferred_day === d.v ? '#fff' : 'var(--tx-2)',
                          }}>
                          {d.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>

            {/* Monthly budget summary */}
            {settings.auto_participate && (
              <div style={{
                marginTop: 8, padding: '10px 14px', borderRadius: 10,
                background: 'rgba(46,166,255,.07)', border: '.5px solid rgba(46,166,255,.2)',
                fontSize: 12, color: 'var(--tx-2)', lineHeight: 1.6,
              }}>
                Max auto-spend:{' '}
                <span className="mono" style={{ color: 'var(--tg)', fontWeight: 700 }}>
                  {fmtCAD(settings.shares_per_round * sharePrice * settings.max_rounds_per_month)}/mo
                </span>
                {' '}· {settings.shares_per_round} share{settings.shares_per_round > 1 ? 's' : ''} ×{' '}
                {fmtCAD(sharePrice)} × {settings.max_rounds_per_month} rounds ·{' '}
                {settings.preferred_day == null ? 'any draw day' :
                  settings.preferred_day === 1 ? 'Tuesdays only' : 'Fridays only'}
              </div>
            )}

            {!user.is_group_trustee && (
              <>
                <SectionHead icon={PersonIcon} label="Become a trustee" />
                <div className="card" style={{ padding: '12px 14px', marginBottom: 8 }}>
                  {trusteeApp?.status === 'pending' ? (
                    <p style={{ fontSize: 13, color: 'var(--tx-2)', margin: 0 }}>
                      Application pending for <strong>{trusteeApp.proposed_group_name}</strong>.
                    </p>
                  ) : trusteeApp?.status === 'rejected' ? (
                    <p style={{ fontSize: 13, color: 'var(--danger)', margin: '0 0 10px' }}>
                      Application rejected{trusteeApp.review_notes ? `: ${trusteeApp.review_notes}` : '.'}
                    </p>
                  ) : (
                    <>
                      <p style={{ fontSize: 12, color: 'var(--tx-3)', margin: '0 0 10px', lineHeight: 1.5 }}>
                        Request your own group to manage rounds and invite friends.
                      </p>
                      <input
                        className="input"
                        placeholder="Your group name"
                        value={groupName}
                        onChange={e => setGroupName(e.target.value)}
                        style={{ marginBottom: 10 }}
                      />
                      <button
                        className="btn btn-primary btn-sm"
                        disabled={applyBusy || !groupName.trim()}
                        onClick={async () => {
                          setApplyBusy(true)
                          try {
                            await api.trustee.apply(groupName.trim())
                            const r = await api.trustee.application()
                            setTrusteeApp(r.application)
                            showToast('Application submitted', 'success')
                          } catch (e) {
                            showToast(e.message, 'error')
                          } finally {
                            setApplyBusy(false)
                          }
                        }}
                      >
                        {applyBusy ? 'Submitting…' : 'Request trustee access'}
                      </button>
                    </>
                  )}
                </div>
              </>
            )}

            {/* ── Legal ── */}
            <SectionHead icon={TicketIcon} label="Agreements" />
            <div className="card" style={{ padding: '12px 14px', marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>Group Prize Agreement</div>
              <p style={{ fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5, margin: '0 0 10px' }}>
                BCLC Group Prize Agreement with your beneficiary details and trustee{' '}
                <strong>{user.trustee?.full_name || user.trustee?.username || 'your group trustee'}</strong>.
                Each round has a separate amendment with your share and draw info.
              </p>
              <AgreementLink kind="master" label="View & download PDF" />
            </div>

            {/* ── Notifications ── */}
            <SectionHead icon={BellIcon} label="Notifications" />

            <div style={{
              background: 'var(--surface)', border: '.5px solid var(--hairline-2)',
              borderRadius: 14, overflow: 'hidden',
            }}>
              {[
                {
                  key: 'notif_new_round', icon: '🎟',
                  label: 'New round opened',
                  sub: 'Alert when admin starts a new draw',
                },
                {
                  key: 'notif_contribution', icon: '💸',
                  label: 'Pool activity',
                  sub: 'When another member adds to a round you joined',
                },
                {
                  key: 'notif_reminder', icon: '⏰',
                  label: 'Closing reminders',
                  sub: '48h & 24h before a round closes to entries',
                },
                {
                  key: 'notif_ticket', icon: '✅',
                  label: 'Ticket purchased',
                  sub: 'Confirmation when ticket is bought',
                },
                {
                  key: 'notif_results', icon: '🏆',
                  label: 'Results & prizes',
                  sub: 'Your winnings when results are entered',
                },
                ...(user?.is_group_trustee ? [{
                  key: 'notif_round_closed', icon: '🎫',
                  label: 'Round closed — buy ticket',
                  sub: 'Alert you when a round closes so you can buy the ticket',
                }] : []),
              ].map(({ key, icon, label, sub }, i, arr) => (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 14px',
                  borderBottom: i < arr.length - 1 ? '.5px solid var(--hairline)' : 'none',
                }}>
                  <span style={{ fontSize: 22, flexShrink: 0 }}>{icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 500 }}>{label}</div>
                    <div style={{ fontSize: 12, color: 'var(--tx-3)', marginTop: 1 }}>{sub}</div>
                  </div>
                  <Toggle on={settings[key]} onChange={v => set(key, v)} />
                </div>
              ))}
            </div>

            {/* ── Save button ── */}
            <button className="btn btn-primary btn-block"
              style={{ marginTop: 20 }}
              disabled={busy}
              onClick={save}>
              {saved ? '✓ Saved!' : busy ? 'Saving…' : 'Save preferences'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
