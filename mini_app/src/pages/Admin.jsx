import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { StatusPill } from '../components/StatusPill.jsx'
import {
  UsersIcon, WalletIcon, TicketIcon, TrophyIcon, ShieldIcon,
  CheckIcon, XIcon, PlusIcon, UploadIcon, SearchIcon,
} from '../components/Icon.jsx'

function compressImage(file, maxPx = 1200, quality = 0.82) {
  return new Promise(resolve => {
    const reader = new FileReader()
    reader.onload = e => {
      const img = new Image()
      img.onload = () => {
        let { width: w, height: h } = img
        if (w > maxPx || h > maxPx) {
          if (w > h) { h = Math.round(h * maxPx / w); w = maxPx }
          else       { w = Math.round(w * maxPx / h); h = maxPx }
        }
        const canvas = document.createElement('canvas')
        canvas.width = w; canvas.height = h
        canvas.getContext('2d').drawImage(img, 0, 0, w, h)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.src = e.target.result
    }
    reader.readAsDataURL(file)
  })
}

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

function fmtDate(s) {
  if (!s) return ''
  const d = new Date(s.includes('T') ? s : s + 'T00:00:00')
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' })
}

const TODAY = new Date().toISOString().slice(0, 10)

function FieldLabel({ label, children, flex }) {
  return (
    <div className="col gap-4" style={{ flex: flex ? 1 : 'initial', minWidth: 0 }}>
      <span style={{ fontSize: 11, color: 'var(--tx-2)', letterSpacing: '.3px', textTransform: 'uppercase', fontWeight: 600 }}>
        {label}
      </span>
      {children}
    </div>
  )
}

function SummaryRow({ k, v, mono }) {
  return (
    <div className="row between" style={{ padding: '9px 0', borderBottom: '.5px solid var(--hairline)' }}>
      <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>{k}</span>
      <span className={mono ? 'mono' : ''} style={{ fontSize: 14, fontWeight: 600 }}>{v}</span>
    </div>
  )
}

const LOTTERY_TYPES = [
  { id: 'lotto_max', name: 'Lotto Max', price: 6, tag: '6/49 + Max' },
  { id: '649',       name: '6/49',      price: 3, tag: '3$/share'   },
]

// ── New Round Sheet ────────────────────────────────────────────────────────
function NewRoundSheet({ onClose, onCreated, showToast }) {
  const [lotteryType, setLotteryType] = useState('lotto_max')
  const [date,     setDate]     = useState('')
  const [jackpot,  setJackpot]  = useState('70000000')
  const [target,   setTarget]   = useState('25')
  const [price,    setPrice]    = useState('6')
  const [busy,     setBusy]     = useState(false)

  function selectType(lt) {
    setLotteryType(lt.id)
    setPrice(String(lt.price))
  }

  async function submit() {
    setBusy(true)
    try {
      const res = await api.admin.newRound({
        lottery_type:    lotteryType,
        jackpot:         Number(jackpot) || 0,
        draw_date:       date || undefined,
        tickets_target:  Number(target)  || 25,
        price_per_share: Number(price)   || 6,
      })
      showToast(`Round #${res.round_id} opened!`, 'success')
      onCreated()
      onClose()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Open new round</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <div className="col" style={{ gap: 12, marginBottom: 16 }}>
            <FieldLabel label="Lottery type">
              <div style={{ display: 'flex', gap: 8 }}>
                {LOTTERY_TYPES.map(lt => (
                  <button key={lt.id} onClick={() => selectType(lt)} style={{
                    flex: 1, padding: '10px 8px', borderRadius: 10, cursor: 'pointer',
                    border: `.5px solid ${lotteryType === lt.id ? 'var(--tg)' : 'var(--hairline-2)'}`,
                    background: lotteryType === lt.id ? 'rgba(46,166,255,.14)' : 'var(--bg-3)',
                    color: lotteryType === lt.id ? 'var(--tg)' : 'var(--tx-1)',
                    fontWeight: 700, fontSize: 14, fontFamily: 'inherit',
                  }}>
                    {lt.name}
                    <div style={{ fontSize: 10, fontWeight: 400, color: lotteryType === lt.id ? 'var(--tg)' : 'var(--tx-3)', marginTop: 2 }}>
                      ${lt.price}/share
                    </div>
                  </button>
                ))}
              </div>
            </FieldLabel>
            <FieldLabel label="Estimated jackpot (CAD)">
              <input className="input mono" type="number" value={jackpot}
                onChange={e => setJackpot(e.target.value)} placeholder="70000000" />
            </FieldLabel>
            <div className="row gap-8">
              <FieldLabel label="Pool target (tickets)" flex>
                <input className="input mono" type="number" value={target}
                  onChange={e => setTarget(e.target.value)} placeholder="25" />
              </FieldLabel>
              <FieldLabel label="Price / share ($)" flex>
                <input className="input mono" type="number" value={price}
                  onChange={e => setPrice(e.target.value)} placeholder="6" />
              </FieldLabel>
            </div>
            <FieldLabel label="Draw date (optional)">
              <input className="input" type="date" min={TODAY} value={date}
                onChange={e => setDate(e.target.value)} />
            </FieldLabel>
          </div>
          <button className="btn btn-primary btn-block" disabled={busy} onClick={submit}>
            <PlusIcon width={16} height={16} />
            {busy ? 'Opening…' : 'Open round'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Upload Ticket Sheet (with camera scan) ───────────────────────────────
function UploadTicketSheet({ round, onClose, onUploaded, showToast }) {
  const [nums,      setNums]      = useState(['', '', '', '', '', '', ''])
  const [busy,      setBusy]      = useState(false)
  const [scanning,  setScanning]  = useState(false)
  const [preview,   setPreview]   = useState(null)   // data URL for thumbnail
  const [scanDate,  setScanDate]  = useState(null)   // draw date from scan
  const fileRef = useRef()

  function setNum(i, v) {
    const c = [...nums]
    c[i] = v.replace(/\D/g, '').slice(0, 2)
    setNums(c)
    if (v.length >= 2 && i < 6) document.getElementById(`tn${i + 1}`)?.focus()
  }

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const dataUrl = await compressImage(file)
    setPreview(dataUrl)
    setScanning(true)
    try {
      const res = await api.admin.scanTicket(round.id, dataUrl)
      if (res.numbers?.length === 7) {
        setNums(res.numbers.map(String))
        showToast('Ticket scanned — numbers pre-filled!', 'success')
      } else {
        showToast('Scan done — verify numbers manually', 'success')
      }
      if (res.draw_date) setScanDate(res.draw_date)
    } catch (err) {
      showToast('Scan failed: ' + err.message, 'error')
    } finally {
      setScanning(false)
    }
  }

  const valid = nums.every(n => n && Number(n) >= 1 && Number(n) <= 50)

  async function submit() {
    setBusy(true)
    try {
      await api.admin.uploadTicket(round.id, nums.map(Number))
      showToast('Ticket numbers uploaded!', 'success')
      onUploaded()
      onClose()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  const dateMismatch = scanDate && round?.draw_date && scanDate !== round.draw_date

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Upload ticket · Round #{round?.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">

          {/* Camera scan section */}
          <input ref={fileRef} type="file" accept="image/*" capture="environment"
            style={{ display: 'none' }} onChange={handleFile} />

          {preview ? (
            <div style={{ position: 'relative', marginBottom: 14 }}>
              <img src={preview} alt="ticket"
                style={{ width: '100%', borderRadius: 12, maxHeight: 200, objectFit: 'cover' }} />
              {scanning && (
                <div style={{
                  position: 'absolute', inset: 0, borderRadius: 12,
                  background: 'rgba(13,20,27,.75)',
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10,
                }}>
                  <div className="spinner" />
                  <span style={{ fontSize: 13, color: '#fff', fontWeight: 600 }}>Scanning ticket…</span>
                </div>
              )}
              {!scanning && (
                <button onClick={() => fileRef.current?.click()}
                  style={{
                    position: 'absolute', bottom: 8, right: 8,
                    background: 'rgba(46,166,255,.9)', color: '#fff',
                    border: 'none', borderRadius: 8, padding: '5px 10px',
                    fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  }}>
                  Rescan
                </button>
              )}
            </div>
          ) : (
            <button className="btn btn-block" onClick={() => fileRef.current?.click()}
              style={{ background: 'rgba(46,166,255,.12)', color: 'var(--tg)', marginBottom: 14, gap: 8 }}>
              <span style={{ fontSize: 20 }}>📷</span>
              Scan ticket photo
            </button>
          )}

          {scanDate && (
            <div style={{
              fontSize: 12, borderRadius: 8, padding: '8px 12px', marginBottom: 12,
              background: dateMismatch ? 'rgba(242,163,59,.1)' : 'rgba(78,208,122,.1)',
              color: dateMismatch ? 'var(--warn)' : 'var(--money)',
              border: `.5px solid ${dateMismatch ? 'rgba(242,163,59,.3)' : 'rgba(78,208,122,.3)'}`,
            }}>
              {dateMismatch
                ? `⚠ Ticket draw date ${scanDate} differs from round draw date ${round.draw_date}`
                : `✓ Draw date confirmed: ${fmtDate(scanDate)}`}
            </div>
          )}

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Ticket numbers (1–50)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6, marginBottom: 16 }}>
            {nums.map((v, i) => (
              <input key={i} id={`tn${i}`} value={v} maxLength={2}
                inputMode="numeric"
                onChange={e => setNum(i, e.target.value)}
                className="input num-input"
                style={{ padding: 0, textAlign: 'center', fontSize: 16, fontWeight: 700, height: 44 }}
              />
            ))}
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <SummaryRow k="Round"        v={`#${round?.id}`} mono />
            <SummaryRow k="Pool total"   v={fmtCAD(round?.pool)} mono />
            <SummaryRow k="Participants" v={round?.participants?.length ?? 0} mono />
            <SummaryRow k="Draw date"    v={round?.draw_date ? fmtDate(round.draw_date) : '—'} />
          </div>

          <button className="btn btn-primary btn-block" disabled={!valid || busy || scanning} onClick={submit}>
            <UploadIcon width={16} height={16} />
            {busy ? 'Uploading…' : scanning ? 'Scanning…' : 'Submit ticket numbers'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Enter Results Sheet ───────────────────────────────────────────────────
function ResultsSheet({ round, onClose, onResults, showToast }) {
  const [nums,       setNums]       = useState(['', '', '', '', '', '', ''])
  const [bonus,      setBonus]      = useState('')
  const [totalPrize, setTotalPrize] = useState('')
  const [busy,       setBusy]       = useState(false)

  function setNum(i, v) {
    const c = [...nums]
    c[i] = v.replace(/\D/g, '').slice(0, 2)
    setNums(c)
    if (v.length >= 2 && i < 6) {
      document.getElementById(`wn${i + 1}`)?.focus()
    }
  }

  const valid = nums.every(n => n && Number(n) >= 1) &&
    bonus && Number(bonus) >= 1 &&
    totalPrize && Number(totalPrize) >= 0

  async function submit() {
    setBusy(true)
    try {
      await api.admin.results(round.id, nums.map(Number), Number(bonus), Number(totalPrize))
      showToast('Results entered — prizes distributed!', 'success')
      onResults()
      onClose()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Enter results · Round #{round?.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <p style={{ fontSize: 13, color: 'var(--tx-2)', marginBottom: 16, lineHeight: 1.5 }}>
            Enter the 7 winning numbers and bonus. Prize allocation is computed
            automatically and distributed to participants proportionally.
          </p>

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Winning numbers
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 6, marginBottom: 12 }}>
            {nums.map((v, i) => (
              <input key={i} id={`wn${i}`} value={v} placeholder="—" maxLength={2}
                inputMode="numeric"
                onChange={e => setNum(i, e.target.value)}
                className="input num-input"
                style={{ padding: 0, textAlign: 'center', fontSize: 16, fontWeight: 700, height: 44 }}
              />
            ))}
          </div>

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Bonus number
          </div>
          <input value={bonus} onChange={e => setBonus(e.target.value.replace(/\D/g, '').slice(0, 2))}
            placeholder="—" maxLength={2} inputMode="numeric"
            className="input num-input"
            style={{ width: 56, padding: 0, textAlign: 'center', fontSize: 16, fontWeight: 700,
                     height: 44, marginBottom: 16 }}
          />

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Total prize won by this pool (CAD)
          </div>
          <input value={totalPrize} onChange={e => setTotalPrize(e.target.value)}
            placeholder="0.00" type="number" inputMode="decimal"
            className="input mono" style={{ marginBottom: 16 }}
          />

          <div className="card" style={{ marginBottom: 16 }}>
            <SummaryRow k="Round"        v={`#${round?.id}`} mono />
            <SummaryRow k="Pool total"   v={fmtCAD(round?.pool)} mono />
            <SummaryRow k="Participants" v={round?.participants?.length ?? 0} mono />
          </div>

          <button className="btn btn-primary btn-block" disabled={!valid || busy} onClick={submit}>
            <TrophyIcon width={16} height={16} />
            {busy ? 'Processing…' : 'Stage results & distribute'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main Admin page ────────────────────────────────────────────────────────
export default function Admin() {
  const [tab,      setTab]      = useState('round')
  const [round,    setRound]    = useState(undefined)
  const [deposits, setDeposits] = useState(null)
  const [imapOk,   setImapOk]  = useState(false)
  const [members,  setMembers]  = useState(null)
  const [busy,     setBusy]     = useState({})
  const [showNew,  setShowNew]  = useState(false)
  const [showUp,   setShowUp]   = useState(false)
  const [showRes,  setShowRes]  = useState(false)
  const showToast = useToast()

  const loadRound    = useCallback(() => api.admin.round().then(d => setRound(d.round)).catch(() => setRound(null)), [])
  const loadDeposits = useCallback(() => api.admin.deposits().then(d => { setDeposits(d.deposits); setImapOk(!!d.imap_configured) }).catch(() => setDeposits([])), [])
  const loadMembers  = useCallback(() => api.admin.members().then(d => setMembers(d.members)).catch(() => setMembers([])), [])

  useEffect(() => { loadRound(); loadDeposits(); loadMembers() }, [])

  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  async function roundAction(key, fn, label) {
    setB(key, true)
    try {
      const res = await fn()
      showToast(label(res), 'success')
      await loadRound()
    } catch (err) { showToast(err.message, 'error') }
    finally { setB(key, false) }
  }

  async function resolveDeposit(id, action) {
    setB(`d${id}`, true)
    try {
      await api.admin.resolve(id, action)
      showToast(action === 'approve' ? 'Deposit approved!' : 'Deposit rejected.', 'success')
      await loadDeposits()
    } catch (err) { showToast(err.message, 'error') }
    finally { setB(`d${id}`, false) }
  }

  const ds       = round?.display_status || round?.status
  const st       = round?.status
  const canOpen  = !round || ['DRAWN','done','drawn'].includes(ds)
  const canClose = st === 'open' || ds === 'OPEN'
  const canUpload = st === 'closed' || st === 'uploaded' || ds === 'UPLOADED' || ds === 'CLOSING'
  const canResults = canUpload || st === 'uploaded'

  const pendingCount = deposits ? deposits.filter(d => d.status === 'pending').length : 0

  return (
    <div className="tab-content">
      {/* Admin header */}
      <div style={{ padding: '12px 16px 4px' }}>
        <div className="row between">
          <div className="row gap-10">
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'rgba(245,199,59,.18)', color: 'var(--gold)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <ShieldIcon width={20} height={20} />
            </div>
            <div className="col gap-4">
              <span style={{ fontSize: 15, fontWeight: 600 }}>Admin dashboard</span>
              <span style={{ fontSize: 11, color: 'var(--tx-2)' }}>Trustee access</span>
            </div>
          </div>
          <span className="chip chip-gold" style={{ padding: '5px 10px' }}>TRUSTEE</span>
        </div>
      </div>

      {/* Metric strip */}
      <div style={{ padding: '10px 16px 0', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        {[
          { Icon: UsersIcon,  label: 'Members', value: members?.length ?? '—',           color: 'var(--tg)'    },
          { Icon: WalletIcon, label: 'Pending', value: pendingCount || '—',              color: 'var(--warn)'  },
          { Icon: TicketIcon, label: 'Pool',    value: round ? fmtCAD(round.pool) : '—', color: 'var(--money)' },
        ].map(({ Icon, label, value, color }) => (
          <div key={label} className="card col gap-4" style={{ padding: '10px 12px' }}>
            <Icon width={14} height={14} style={{ color }} />
            <span className="mono" style={{ fontSize: 16, fontWeight: 700, color }}>{value}</span>
            <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Tab strip */}
      <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8 }}>
        {[
          { id: 'round',    label: 'Round'   },
          { id: 'deposits', label: pendingCount ? `Deposits (${pendingCount})` : 'Deposits' },
          { id: 'members',  label: 'Members' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
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
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
              <div className="spinner" />
            </div>
          ) : round ? (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="row between" style={{ marginBottom: 12 }}>
                <span style={{ fontSize: 15, fontWeight: 700 }}>Round #{round.id}</span>
                <StatusPill status={ds} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                {[
                  ['Pool',         fmtCAD(round.pool)],
                  ['Participants', round.participants?.length ?? 0],
                  ['Jackpot',      round.jackpot ? `$${(round.jackpot / 1_000_000).toFixed(0)}M` : '—'],
                  ['Draw date',    round.draw_date ? fmtDate(round.draw_date) : '—'],
                ].map(([k, v]) => (
                  <div key={k} className="col gap-4">
                    <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{k}</span>
                    <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>

              {round.participants?.length > 0 && (
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

              {round.ticket_numbers && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  <div style={{ fontSize: 11, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Ticket numbers
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {JSON.parse(round.ticket_numbers || '[]').map(n => (
                      <span key={n} className="ball md white">{n}</span>
                    ))}
                  </div>
                </>
              )}

              {round.ticket_image && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '12px 0 12px' }} />
                  <div style={{ fontSize: 11, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Ticket photo
                  </div>
                  <img src={round.ticket_image} alt="Lotto ticket"
                    style={{ width: '100%', borderRadius: 10, maxHeight: 220, objectFit: 'cover' }} />
                </>
              )}

              {round.winning_numbers && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  <div style={{ fontSize: 11, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Winning numbers
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {JSON.parse(round.winning_numbers || '[]').map(n => (
                      <span key={n} className="ball md match">{n}</span>
                    ))}
                    {round.bonus_number && (
                      <>
                        <span style={{ color: 'var(--tx-3)', fontSize: 18, fontWeight: 700 }}>+</span>
                        <span className="ball md bonus">{round.bonus_number}</span>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
          ) : null}

          {/* Actions */}
          <div className="col" style={{ gap: 8 }}>
            <button className="btn btn-primary btn-block"
              disabled={!canOpen || busy.new}
              style={{ opacity: canOpen ? 1 : .4 }}
              onClick={() => setShowNew(true)}>
              <PlusIcon width={16} height={16} />
              Open new round
            </button>
            <button className="btn btn-block"
              style={{ background: 'var(--surface-2)', opacity: canClose ? 1 : .4 }}
              disabled={!canClose || busy.close}
              onClick={() => roundAction('close', api.admin.closeRound, r => `Round #${r.round_id} closed.`)}>
              {busy.close ? 'Closing…' : 'Close round'}
            </button>
            <button className="btn btn-block"
              style={{ background: canUpload ? 'rgba(46,166,255,.12)' : 'var(--surface-2)',
                       color: canUpload ? 'var(--tg)' : undefined, opacity: canUpload ? 1 : .4 }}
              disabled={!canUpload || !round}
              onClick={() => setShowUp(true)}>
              <UploadIcon width={16} height={16} />
              Upload ticket numbers
            </button>
            <button className="btn btn-block"
              style={{ background: canResults ? 'rgba(245,199,59,.12)' : 'var(--surface-2)',
                       color: canResults ? 'var(--gold)' : undefined, opacity: canResults ? 1 : .4 }}
              disabled={!canResults || !round}
              onClick={() => setShowRes(true)}>
              <TrophyIcon width={16} height={16} />
              Enter results
            </button>
          </div>
        </div>
      )}

      {/* ── Deposits tab ── */}
      {tab === 'deposits' && (
        <div style={{ padding: '12px 16px 24px' }}>
          {imapOk && (
            <button className="btn btn-block" style={{ marginBottom: 12,
              background: 'rgba(46,166,255,.12)', color: 'var(--tg)' }}
              disabled={busy.imap}
              onClick={async () => {
                setB('imap', true)
                try {
                  const r = await api.admin.checkEtransfer()
                  showToast(r.approved > 0
                    ? `✅ Auto-approved ${r.approved} e-transfer(s)!`
                    : `Checked ${r.checked} email(s) — nothing new.`, 'success')
                  await loadDeposits()
                } catch (err) { showToast(err.message, 'error') }
                finally { setB('imap', false) }
              }}>
              {busy.imap ? 'Checking…' : '📧 Check e-transfers'}
            </button>
          )}
          {!deposits ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
              <div className="spinner" />
            </div>
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
                    fontSize: 14, fontWeight: 700, color: 'var(--tg)', flexShrink: 0,
                  }}>
                    {(d.full_name || '?')[0].toUpperCase()}
                  </div>
                  <div className="col gap-4">
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{d.full_name}</span>
                    {d.username && <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>@{d.username}</span>}
                    {d.ref_code && (
                      <span style={{ fontSize: 11, color: 'var(--tg)', fontFamily: 'var(--mono)', fontWeight: 600 }}>
                        {d.ref_code}
                      </span>
                    )}
                  </div>
                </div>
                <div className="col" style={{ textAlign: 'right', gap: 2 }}>
                  <span className="mono" style={{ fontSize: 18, fontWeight: 700, color: 'var(--money)' }}>
                    {fmtCAD(d.amount)}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--tx-3)' }}>
                    {d.payment_method === 'etransfer' ? '🏦 e-Transfer' : '💳 card'} · {d.created_at?.slice(0, 10)}
                  </span>
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
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
              <div className="spinner" />
            </div>
          ) : (
            <div className="card" style={{ padding: 0 }}>
              {members.map((m, idx) => (
                <div key={m.telegram_id} style={{
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
                      {m.is_trustee && (
                        <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--gold)', fontWeight: 700 }}>TRUSTEE</span>
                      )}
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

      {/* Sheets */}
      {showNew && (
        <NewRoundSheet
          onClose={() => setShowNew(false)}
          onCreated={loadRound}
          showToast={showToast}
        />
      )}
      {showUp && round && (
        <UploadTicketSheet
          round={round}
          onClose={() => setShowUp(false)}
          onUploaded={loadRound}
          showToast={showToast}
        />
      )}
      {showRes && round && (
        <ResultsSheet
          round={round}
          onClose={() => setShowRes(false)}
          onResults={loadRound}
          showToast={showToast}
        />
      )}
    </div>
  )
}
