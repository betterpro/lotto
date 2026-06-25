import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { StatusPill } from '../components/StatusPill.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'
import {
  LOTTERY_TYPES, lotteryMeta, ticketLayout, emptyTicketRows,
  parseTicketNumbers, ticketRowsValid, ticketRowsToNumbers, mergeScannedRows,
  isVariableRowLayout, rowSpecForIndex, addTicketRow, removeTicketRow,
  JACKPOT_PENDING_LABEL, fmtJackpotCompact,
} from '../lottery.js'
import LotteryLogo from '../components/LotteryLogo.jsx'
import CameraCapture from '../components/CameraCapture.jsx'
import { scanTicketImage } from '../ticketOcr.js'
import {
  UsersIcon, WalletIcon, TicketIcon, TrophyIcon, ShieldIcon,
  CheckIcon, XIcon, PlusIcon, UploadIcon, SearchIcon, CameraIcon,
} from '../components/Icon.jsx'

function compressImage(file, maxPx = 1568, quality = 0.9) {
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

function TicketNumbersView({ ticketNumbers, lotteryType, selectable, selectedMain = [], bonus, pickBonus, onPick }) {
  const layout = ticketLayout(lotteryType)
  const rows = parseTicketNumbers(ticketNumbers)
  if (!rows.length) return null
  const multi = isVariableRowLayout(layout) || layout.rows.length > 1
  const mainSet = new Set(selectedMain.map(Number))
  const bonusN = bonus ? Number(bonus) : null

  function ballClass(n) {
    const v = Number(n)
    if (bonusN === v) return 'bonus'
    if (mainSet.has(v)) return 'match'
    return 'white'
  }

  return (
    <div className="col" style={{ gap: 10 }}>
      {rows.map((row, i) => {
        const spec = rowSpecForIndex(layout, i)
        return (
          <div key={`${spec.label}-${i}`}>
            {multi && (
              <div style={{ fontSize: 12, color: 'var(--tx-3)', marginBottom: 6, fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '.3px' }}>
                {spec.label}
              </div>
            )}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {row.map((n, j) => {
                const cls = ballClass(n)
                if (selectable) {
                  return (
                    <button key={`${i}-${j}`} type="button" onClick={() => onPick(n)}
                      style={{
                        border: 'none', background: 'none', padding: 0, cursor: 'pointer',
                        opacity: pickBonus && cls === 'white' ? 0.85 : 1,
                      }}>
                      <span className={`ball md ${cls}`}>{n}</span>
                    </button>
                  )
                }
                return <span key={`${i}-${j}`} className={`ball md ${cls}`}>{n}</span>
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function FieldLabel({ label, children, flex }) {
  return (
    <div className="col gap-4" style={{ flex: flex ? 1 : 'initial', minWidth: 0 }}>
      <span style={{ fontSize: 12, color: 'var(--tx-2)', letterSpacing: '.3px', textTransform: 'uppercase', fontWeight: 600 }}>
        {label}
      </span>
      {children}
    </div>
  )
}

function SummaryRow({ k, v, mono }) {
  return (
    <div className="row between" style={{ padding: '9px 0', borderBottom: '.5px solid var(--hairline)' }}>
      <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>{k}</span>
      <span className={mono ? 'mono' : ''} style={{ fontSize: 15, fontWeight: 600 }}>{v}</span>
    </div>
  )
}

// ── New Round Sheet ────────────────────────────────────────────────────────
function NewRoundSheet({ onClose, onCreated, showToast }) {
  const [lotteryType, setLotteryType] = useState('lotto_max')
  const [date,     setDate]     = useState('')
  const [drawDates, setDrawDates] = useState([])
  const [jackpot,  setJackpot]  = useState(0)
  const [jackpotAvailable, setJackpotAvailable] = useState(false)
  const [nextDrawDate, setNextDrawDate] = useState('')
  const [target,   setTarget]   = useState('25')
  const [price,    setPrice]    = useState('6')
  const [busy,     setBusy]     = useState(false)
  const [suggesting, setSuggesting] = useState(false)

  useEffect(() => {
    let cancelled = false
    setSuggesting(true)
    api.admin.suggestRound(lotteryType, date || undefined)
      .then(res => {
        if (cancelled) return
        const dates = res.draw_dates || []
        setDrawDates(dates)
        if (!date && res.draw_date) setDate(res.draw_date)
        else if (date && dates.length && !dates.includes(date)) setDate(res.draw_date || dates[0] || '')
        setJackpotAvailable(!!res.jackpot_available)
        setJackpot(res.jackpot || 0)
        setNextDrawDate(res.next_draw_date || '')
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setSuggesting(false) })
    return () => { cancelled = true }
  }, [lotteryType, date])

  function selectType(lt) {
    setLotteryType(lt.id)
    setPrice(String(lt.price))
    setDate('')
    setDrawDates([])
    setJackpot(0)
    setJackpotAvailable(false)
    setNextDrawDate('')
  }

  async function submit() {
    if (!date) {
      showToast('Choose a draw date', 'error')
      return
    }
    setBusy(true)
    try {
      const res = await api.admin.newRound({
        lottery_type:    lotteryType,
        draw_date:       date,
        tickets_target:  target === '' ? 0 : (Number(target) || 0),
        price_per_share: Number(price)   || 6,
      })
      showToast(`Round #${res.round_no ?? res.round_id} opened!`, 'success')
      onCreated(res.round_id)
      onClose()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  const jackpotText = suggesting
    ? 'Loading…'
    : jackpotAvailable
      ? `$${fmtJackpotCompact(jackpot)} CAD`
      : JACKPOT_PENDING_LABEL
  const isFutureDraw = date && nextDrawDate && date !== nextDrawDate

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
              <div style={{ display: 'flex', gap: 10 }}>
                {LOTTERY_TYPES.map(lt => {
                  const selected = lotteryType === lt.id
                  return (
                    <button key={lt.id} onClick={() => selectType(lt)} style={{
                      flex: 1, padding: '12px 10px 10px', borderRadius: 12, cursor: 'pointer',
                      border: `.5px solid ${selected ? 'var(--tg)' : 'var(--hairline-2)'}`,
                      background: selected ? 'rgba(46,166,255,.12)' : 'var(--bg-3)',
                      color: selected ? 'var(--tg)' : 'var(--tx-1)',
                      fontFamily: 'inherit', display: 'flex', flexDirection: 'column',
                      alignItems: 'center', gap: 8,
                    }}>
                      <LotteryLogo type={lt.id} height={40} style={{ width: '100%' }} />
                      <div style={{ fontWeight: 700, fontSize: 14 }}>{lt.name}</div>
                      <div style={{
                        fontSize: 12, fontWeight: 500,
                        color: selected ? 'var(--tg)' : 'var(--tx-3)',
                      }}>
                        ${lt.price}/share
                      </div>
                    </button>
                  )
                })}
              </div>
            </FieldLabel>

            <FieldLabel label={`Draw date${suggesting && !drawDates.length ? ' · loading…' : ''}`}>
              {drawDates.length === 0 ? (
                <div className="input" style={{ color: 'var(--tx-3)', fontStyle: 'italic' }}>
                  {suggesting ? 'Loading draws…' : 'No upcoming draws'}
                </div>
              ) : (
                <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 2 }}>
                  {drawDates.map((d, i) => {
                    const sel = d === date
                    return (
                      <button key={d} type="button" onClick={() => setDate(d)} style={{
                        flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                        gap: 2, padding: '10px 12px', borderRadius: 10, cursor: 'pointer', border: 'none',
                        background: sel ? 'rgba(46,166,255,.16)' : 'var(--surface-2)',
                        outline: sel ? '1.5px solid var(--tg)' : '1.5px solid transparent',
                        fontFamily: 'inherit', textAlign: 'left', minWidth: 96,
                      }}>
                        {i === 0 && (
                          <span style={{
                            fontSize: 11, fontWeight: 700, letterSpacing: '.4px',
                            textTransform: 'uppercase', color: sel ? 'var(--tg)' : 'var(--money)',
                          }}>
                            Next
                          </span>
                        )}
                        <span style={{
                          fontSize: 14, fontWeight: 600,
                          color: sel ? 'var(--tg)' : 'var(--tx-1)',
                        }}>
                          {fmtDate(d)}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </FieldLabel>

            <FieldLabel label={`Estimated jackpot${suggesting ? ' · loading…' : ''}`}>
              <div className="input" style={{
                display: 'flex', alignItems: 'center', minHeight: 44,
                color: jackpotAvailable ? 'var(--tx-1)' : 'var(--tx-3)',
                fontStyle: jackpotAvailable ? 'normal' : 'italic',
                fontWeight: jackpotAvailable ? 600 : 400,
                opacity: jackpotAvailable ? 1 : 0.72,
                background: jackpotAvailable ? undefined : 'var(--bg-3)',
                cursor: 'not-allowed',
              }}>
                {jackpotText}
              </div>
              {!suggesting && !jackpotAvailable && (
                <span style={{ fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.45 }}>
                  {isFutureDraw
                    ? 'Not published for this draw yet. You can open the round now and set the jackpot later.'
                    : 'Not published yet. Open the round and set it later, or it will fill in automatically when lotto.ca publishes it.'}
                </span>
              )}
            </FieldLabel>
            <div className="row gap-8">
              <FieldLabel label="Pool target (blank = no limit)" flex>
                <input className="input mono" type="number" value={target}
                  onChange={e => setTarget(e.target.value)} placeholder="No limit" />
              </FieldLabel>
              <FieldLabel label="Price / share ($)" flex>
                <input className="input mono" type="number" value={price}
                  onChange={e => setPrice(e.target.value)} placeholder="6" />
              </FieldLabel>
            </div>
          </div>
          <button className="btn btn-primary btn-block" disabled={busy || !date || !drawDates.length} onClick={submit}>
            <PlusIcon width={16} height={16} />
            {busy ? 'Opening…' : 'Open round'}
          </button>
        </div>
      </div>
    </div>
  )
}

function RoundJackpotEditor({ round, onUpdated, showToast }) {
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  if (!round?.jackpot_pending) {
    return (
      <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
        ${fmtJackpotCompact(round.jackpot)}
      </span>
    )
  }

  async function saveManual() {
    const jackpot = Number(value)
    if (!jackpot || jackpot < 1) {
      showToast('Enter jackpot in CAD (e.g. 15000000)', 'error')
      return
    }
    setBusy(true)
    try {
      await api.admin.setJackpot(round.id, { jackpot })
      showToast('Jackpot saved', 'success')
      setValue('')
      await onUpdated()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  async function fetchFromSite() {
    setBusy(true)
    try {
      const res = await api.admin.setJackpot(round.id, { fetch: true })
      showToast(`Jackpot set · $${fmtJackpotCompact(res.jackpot)}`, 'success')
      await onUpdated()
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  return (
    <div className="col gap-8">
      <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--tx-3)', fontStyle: 'italic' }}>
        {JACKPOT_PENDING_LABEL}
      </span>
      <input
        className="input mono"
        type="number"
        value={value}
        onChange={e => setValue(e.target.value)}
        placeholder="15000000"
        disabled={busy}
      />
      <span style={{ fontSize: 12, color: 'var(--tx-3)', marginTop: -4 }}>
        Full amount in CAD · e.g. 15000000 for $15M
      </span>
      <div className="row gap-8">
        <button className="btn btn-secondary" style={{ flex: 1 }} disabled={busy} onClick={saveManual}>
          Save jackpot
        </button>
        {round.jackpot_fetchable && (
          <button className="btn btn-secondary" style={{ flex: 1 }} disabled={busy} onClick={fetchFromSite}>
            {busy ? '…' : 'Fetch from lotto site'}
          </button>
        )}
      </div>
      {!round.jackpot_fetchable && (
        <span style={{ fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.4 }}>
          Auto-fetch becomes available when this draw is the next one on lotto.ca.
        </span>
      )}
    </div>
  )
}

// ── Upload Ticket Sheet (camera + Tesseract OCR, multi-ticket) ───────────
/** Order-independent signature of a ticket's rows, for duplicate detection. */
function rowsSignature(rows) {
  const norm = (rows || [])
    .map(r => (r || []).map(Number).filter(n => Number.isFinite(n) && n > 0).sort((a, b) => a - b))
    .filter(r => r.length)
    .map(r => r.join('-'))
    .sort()
  return norm.length ? norm.join('|') : ''
}

function UploadTicketSheet({ round, onClose, onUploaded, showToast }) {
  const layout = ticketLayout(round?.lottery_type)
  const variableRows = isVariableRowLayout(layout)
  const required = round?.tickets_required ?? 1
  const savedTickets = (round?.round_tickets || []).filter(t => t?.rows?.length)
  const alreadySaved = savedTickets.length
  const savedSignatures = savedTickets.map(t => rowsSignature(t.rows)).filter(Boolean)

  // Each collected ticket: { id, image, rows, drawDate, scanning, error }
  const [tickets, setTickets] = useState([])
  const [cameraOpen, setCameraOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const idRef = useRef(0)
  const galleryRef = useRef()
  const cameraFileRef = useRef()

  // Map of ticketId -> duplicate reason ('saved' | 'batch'), derived each render.
  const dups = (() => {
    const seen = new Map()
    savedSignatures.forEach(sig => seen.set(sig, 'saved'))
    const out = {}
    for (const t of tickets) {
      const sig = rowsSignature(t.rows)
      if (!sig) continue
      if (seen.has(sig)) out[t.id] = seen.get(sig) === 'saved' ? 'saved' : 'batch'
      else seen.set(sig, t.id)
    }
    return out
  })()

  async function scanInto(id, dataUrl) {
    try {
      let scanned = []
      let date = null
      try {
        const r = await api.admin.scanTicket(round.id, dataUrl, { preview: true })
        scanned = Array.isArray(r.rows) ? r.rows : []
        date = r.draw_date || null
      } catch {
        scanned = await scanTicketImage(dataUrl, round.lottery_type, () => {})
      }
      const merged = scanned.length ? mergeScannedRows(scanned, layout) : emptyTicketRows(layout)
      let isDup = false
      setTickets(ts => {
        const next = ts.map(t => t.id === id
          ? { ...t, rows: merged, drawDate: date || t.drawDate, scanning: false }
          : t)
        const sig = rowsSignature(merged)
        if (sig) {
          const others = next.filter(t => t.id !== id).map(t => rowsSignature(t.rows))
          isDup = savedSignatures.includes(sig) || others.includes(sig)
        }
        return next
      })
      if (isDup) {
        queueMicrotask(() => showToast('Duplicate ticket — it won’t be saved twice', 'info'))
      }
    } catch (e) {
      setTickets(ts => ts.map(t => t.id === id ? { ...t, scanning: false, error: e.message } : t))
    }
  }

  function addCapture(dataUrl) {
    if (!dataUrl) return
    const id = ++idRef.current
    setTickets(ts => [...ts, {
      id, image: dataUrl, rows: emptyTicketRows(layout), drawDate: null, scanning: true,
    }])
    scanInto(id, dataUrl)
  }

  async function handleFiles(fileList) {
    const files = Array.from(fileList || [])
    for (const f of files) {
      // eslint-disable-next-line no-await-in-loop
      addCapture(await compressImage(f))
    }
  }

  function openCamera() {
    if (navigator.mediaDevices?.getUserMedia) { setCameraOpen(true); return }
    cameraFileRef.current?.click()
  }

  function setTicketNum(id, rowIdx, colIdx, value, spec) {
    const maxLen = spec.max >= 10 ? 2 : 1
    const v = value.replace(/\D/g, '').slice(0, maxLen)
    setTickets(ts => ts.map(t => {
      if (t.id !== id) return t
      const rows = t.rows.map((row, ri) =>
        ri === rowIdx ? row.map((c, ci) => (ci === colIdx ? v : c)) : [...row])
      return { ...t, rows }
    }))
    if (v.length >= maxLen && colIdx < spec.count - 1) {
      document.getElementById(`tn-${id}-${rowIdx}-${colIdx + 1}`)?.focus()
    }
  }

  function updateTicketRows(id, fn) {
    setTickets(ts => ts.map(t => t.id === id ? { ...t, rows: fn(t.rows) } : t))
  }
  function removeTicket(id) {
    setTickets(ts => ts.filter(t => t.id !== id))
  }

  const anyScanning = tickets.some(t => t.scanning)
  const readyTickets = tickets.filter(t => !t.scanning && !dups[t.id] && ticketRowsValid(t.rows, layout))
  const dupCount = Object.keys(dups).length
  const invalidCount = tickets.filter(t => !t.scanning && !dups[t.id] && !ticketRowsValid(t.rows, layout)).length
  const totalAfterSave = alreadySaved + readyTickets.length
  const mismatchDates = [...new Set(tickets.map(t => t.drawDate).filter(Boolean))]
    .filter(d => round?.draw_date && d !== round.draw_date)

  async function saveAll() {
    if (busy || !readyTickets.length) return
    setBusy(true)
    try {
      let idx = alreadySaved
      for (const t of readyTickets) {
        const nums = ticketRowsToNumbers(t.rows)
        // eslint-disable-next-line no-await-in-loop
        await api.admin.saveTicket(round.id, idx, nums, t.image, t.drawDate || undefined)
        idx++
      }
      if (idx >= required) {
        await api.admin.uploadTicket(round.id)
        showToast(`All ${required} ticket${required === 1 ? '' : 's'} uploaded!`, 'success')
      } else {
        showToast(`Saved ${idx} of ${required} — scan ${required - idx} more`, 'info')
      }
      onUploaded()
      onClose()
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Scan tickets · Round #{round?.group_seq ?? round?.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">

          <div style={{
            fontSize: 13, borderRadius: 8, padding: '8px 12px', marginBottom: 12,
            background: totalAfterSave >= required ? 'rgba(78,208,122,.1)' : 'rgba(46,166,255,.1)',
            color: totalAfterSave >= required ? 'var(--money)' : 'var(--tg)',
            border: `.5px solid ${totalAfterSave >= required ? 'rgba(78,208,122,.3)' : 'rgba(46,166,255,.25)'}`,
          }}>
            {totalAfterSave} of {required} ticket{required === 1 ? '' : 's'} ready
            {required > 1 && ' · capture one photo per physical ticket bought in the pool'}
          </div>

          <input ref={galleryRef} type="file" accept="image/*" multiple
            style={{ display: 'none' }}
            onChange={e => { handleFiles(e.target.files); e.target.value = '' }} />
          <input ref={cameraFileRef} type="file" accept="image/*" capture="environment"
            style={{ display: 'none' }}
            onChange={e => { handleFiles(e.target.files); e.target.value = '' }} />

          {cameraOpen && (
            <CameraCapture
              series
              captured={alreadySaved + tickets.length}
              target={required}
              thumbs={tickets.map(t => t.image)}
              onCapture={addCapture}
              onClose={() => setCameraOpen(false)}
              onError={msg => showToast(msg, 'error')}
            />
          )}

          {tickets.length === 0 ? (
            <>
              <div style={{
                fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.6, marginBottom: 14,
                background: 'var(--bg-3)', borderRadius: 12, padding: 12,
              }}>
                <div style={{ fontWeight: 700, color: 'var(--tx-1)', marginBottom: 6 }}>
                  📸 Tips for a clean scan
                </div>
                • Lay each ticket flat on a dark surface<br />
                • Fill the frame so every number row shows<br />
                • Avoid glare, shadows and blur<br />
                {required > 1 && <>• Capture all {required} tickets in one go — no need to come back</>}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button type="button" className="btn btn-primary btn-block" onClick={openCamera}>
                  <CameraIcon width={18} height={18} />
                  {required > 1 ? `Scan ${required} tickets` : 'Scan ticket'}
                </button>
                <button type="button" className="btn btn-block"
                  style={{ flex: 1, gap: 8, background: 'rgba(46,166,255,.12)', color: 'var(--tg)',
                    border: '.5px solid rgba(46,166,255,.25)' }}
                  onClick={() => galleryRef.current?.click()}>
                  <UploadIcon width={18} height={18} /> Upload
                </button>
              </div>
            </>
          ) : (
            <>
              {(dupCount > 0 || mismatchDates.length > 0) && (
                <div style={{
                  fontSize: 13, borderRadius: 8, padding: '8px 12px', marginBottom: 12,
                  background: 'rgba(242,163,59,.1)', color: 'var(--warn)',
                  border: '.5px solid rgba(242,163,59,.3)', lineHeight: 1.5,
                }}>
                  {dupCount > 0 && <div>⚠ {dupCount} duplicate ticket{dupCount === 1 ? '' : 's'} found — won’t be saved.</div>}
                  {mismatchDates.length > 0 && (
                    <div>⚠ Some tickets show a different draw date ({mismatchDates.join(', ')}) than this round.</div>
                  )}
                </div>
              )}

              <div className="col" style={{ gap: 12, marginBottom: 14 }}>
                {tickets.map((t, i) => {
                  const dup = dups[t.id]
                  const valid = ticketRowsValid(t.rows, layout)
                  const border = dup ? 'rgba(242,163,59,.5)'
                    : t.scanning ? 'var(--hairline)'
                    : valid ? 'rgba(78,208,122,.4)' : 'rgba(242,107,107,.4)'
                  return (
                    <div key={t.id} className="card" style={{ border: `.5px solid ${border}`, padding: 10 }}>
                      <div className="row between" style={{ marginBottom: 8 }}>
                        <div className="row gap-10" style={{ alignItems: 'center' }}>
                          <img src={t.image} alt="" style={{ width: 44, height: 44, borderRadius: 8, objectFit: 'cover' }} />
                          <div className="col">
                            <span style={{ fontSize: 14, fontWeight: 700 }}>Ticket {i + 1}</span>
                            <span style={{ fontSize: 12,
                              color: dup ? 'var(--warn)' : t.scanning ? 'var(--tx-3)' : valid ? 'var(--money)' : 'var(--danger)' }}>
                              {t.scanning ? 'Reading…' : dup ? (dup === 'saved' ? 'Already saved' : 'Duplicate') : valid ? 'Ready' : 'Check numbers'}
                            </span>
                          </div>
                        </div>
                        <button type="button" onClick={() => removeTicket(t.id)}
                          style={{ background: 'none', border: 'none', color: 'var(--danger)',
                            fontSize: 13, fontWeight: 600, cursor: 'pointer', padding: 4 }}>
                          Remove
                        </button>
                      </div>

                      {t.scanning ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', color: 'var(--tx-2)', fontSize: 13 }}>
                          <div className="spinner" style={{ width: 16, height: 16 }} /> Reading numbers…
                        </div>
                      ) : (
                        <div className="col" style={{ gap: 10 }}>
                          {t.rows.map((_, rowIdx) => {
                            const spec = rowSpecForIndex(layout, rowIdx)
                            return (
                              <div key={rowIdx}>
                                <div className="row between" style={{ marginBottom: 4 }}>
                                  <span style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600,
                                    textTransform: 'uppercase', letterSpacing: '.3px' }}>
                                    {spec.label} ({spec.min}–{spec.max})
                                  </span>
                                  {variableRows && t.rows.length > 1 && (
                                    <button type="button"
                                      onClick={() => updateTicketRows(t.id, rows => removeTicketRow(layout, rows, rowIdx))}
                                      style={{ background: 'none', border: 'none', color: 'var(--danger)',
                                        fontSize: 12, fontWeight: 600, cursor: 'pointer', padding: 0 }}>
                                      Remove line
                                    </button>
                                  )}
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${spec.count}, 1fr)`, gap: 5 }}>
                                  {(t.rows[rowIdx] || []).map((v, colIdx) => (
                                    <input key={colIdx} id={`tn-${t.id}-${rowIdx}-${colIdx}`}
                                      value={v} maxLength={spec.max >= 10 ? 2 : 1} inputMode="numeric"
                                      onChange={e => setTicketNum(t.id, rowIdx, colIdx, e.target.value, spec)}
                                      className="input num-input"
                                      style={{ padding: 0, textAlign: 'center', fontSize: 16, fontWeight: 700, height: 40 }} />
                                  ))}
                                </div>
                              </div>
                            )
                          })}
                          {variableRows && t.rows.length < (layout.maxRows ?? 10) && (
                            <button type="button" className="btn btn-block"
                              style={{ background: 'var(--surface-2)', fontSize: 13, padding: '6px' }}
                              onClick={() => updateTicketRows(t.id, rows => addTicketRow(layout, rows))}>
                              <PlusIcon width={13} height={13} /> Add line
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              <button type="button" className="btn btn-block"
                style={{ marginBottom: 10, gap: 8, background: 'rgba(46,166,255,.12)',
                  color: 'var(--tg)', border: '.5px solid rgba(46,166,255,.25)' }}
                onClick={openCamera}>
                <CameraIcon width={16} height={16} /> Scan more
              </button>

              <button className="btn btn-primary btn-block"
                disabled={busy || anyScanning || !readyTickets.length}
                onClick={saveAll}>
                <UploadIcon width={16} height={16} />
                {busy ? 'Saving…'
                  : anyScanning ? 'Reading…'
                  : totalAfterSave >= required
                    ? `Save & notify group (${readyTickets.length})`
                    : `Save ${readyTickets.length} ticket${readyTickets.length === 1 ? '' : 's'}`}
              </button>
              {invalidCount > 0 && (
                <p style={{ fontSize: 12, color: 'var(--tx-3)', textAlign: 'center', marginTop: 8 }}>
                  {invalidCount} ticket{invalidCount === 1 ? '' : 's'} need fixing before they can be saved.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

const WINNING_MAIN_COUNT = 7

// ── Enter Results Sheet ───────────────────────────────────────────────────
function ResultsSheet({ round, onClose, onResults, showToast }) {
  const ticketRows = parseTicketNumbers(round?.ticket_numbers)
  const hasTickets = ticketRows.length > 0

  const [mainNums,   setMainNums]   = useState([])
  const [nums,       setNums]       = useState(() => Array(WINNING_MAIN_COUNT).fill(''))
  const [bonus,      setBonus]      = useState('')
  const [pickBonus,  setPickBonus]  = useState(false)
  const [totalPrize, setTotalPrize] = useState('')
  const [freeTickets, setFreeTickets] = useState('')
  const [busy,       setBusy]       = useState(false)

  function setNum(i, v) {
    const c = [...nums]
    c[i] = v.replace(/\D/g, '').slice(0, 2)
    setNums(c)
    if (v.length >= 2 && i < WINNING_MAIN_COUNT - 1) {
      document.getElementById(`wn${i + 1}`)?.focus()
    }
  }

  function pickFromTicket(n) {
    const v = Number(n)
    if (!Number.isFinite(v) || v < 1) return

    if (pickBonus) {
      setBonus(String(v))
      setPickBonus(false)
      setMainNums(prev => prev.filter(x => x !== v))
      return
    }

    if (mainNums.includes(v)) {
      setMainNums(prev => prev.filter(x => x !== v))
      return
    }
    if (Number(bonus) === v) {
      setBonus('')
      return
    }
    if (mainNums.length < WINNING_MAIN_COUNT) {
      setMainNums(prev => [...prev, v])
    }
  }

  function clearBonus() {
    setBonus('')
    setPickBonus(false)
  }

  const winningNumbers = hasTickets ? mainNums : nums.map(Number)
  const cashPrize = totalPrize === '' ? 0 : Number(totalPrize)
  const freeTicketCount = freeTickets === '' ? 0 : Number(freeTickets)
  const valid = (hasTickets
    ? mainNums.length === WINNING_MAIN_COUNT
    : nums.every(n => n && Number(n) >= 1)) &&
    bonus && Number(bonus) >= 1 &&
    (cashPrize >= 0 && freeTicketCount >= 0) &&
    (cashPrize > 0 || freeTicketCount > 0)

  async function submit() {
    setBusy(true)
    try {
      await api.admin.results(round.id, winningNumbers, Number(bonus), cashPrize, freeTicketCount)
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
          <span className="sheet-title">Enter results · Round #{round?.group_seq ?? round?.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <p style={{ fontSize: 14, color: 'var(--tx-2)', marginBottom: 16, lineHeight: 1.5 }}>
            {hasTickets
              ? 'Tap numbers from the ticket to set the 7 winning numbers and bonus. Prize allocation is computed automatically.'
              : 'Enter the 7 winning numbers and bonus. Prize allocation is computed automatically and distributed to participants proportionally.'}
          </p>

          <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Winning numbers
          </div>

          {hasTickets ? (
            <>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                {Array.from({ length: WINNING_MAIN_COUNT }, (_, i) => {
                  const n = mainNums[i]
                  return n != null ? (
                    <button key={i} type="button" onClick={() => pickFromTicket(n)}
                      style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer' }}>
                      <span className="ball md match">{n}</span>
                    </button>
                  ) : (
                    <span key={i} className="ball md def" style={{ opacity: 0.35 }}>—</span>
                  )
                })}
                <span style={{ color: 'var(--tx-3)', fontSize: 19, fontWeight: 700 }}>+</span>
                <button type="button" onClick={() => (bonus ? clearBonus() : setPickBonus(true))}
                  style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer' }}>
                  <span className={`ball md ${bonus ? 'bonus' : 'def'}`}
                    style={pickBonus ? { outline: '2px solid var(--gold)', outlineOffset: 2 } : undefined}>
                    {bonus || '—'}
                  </span>
                </button>
              </div>
              {pickBonus && (
                <p style={{ fontSize: 13, color: 'var(--gold)', marginBottom: 10 }}>
                  Tap a ticket number for the bonus
                </p>
              )}

              <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, letterSpacing: '.3px',
                            textTransform: 'uppercase', marginBottom: 8 }}>
                Ticket numbers
              </div>
              <TicketNumbersView
                ticketNumbers={round.ticket_numbers}
                lotteryType={round.lottery_type}
                selectable
                selectedMain={mainNums}
                bonus={bonus}
                pickBonus={pickBonus}
                onPick={pickFromTicket}
              />
            </>
          ) : (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${WINNING_MAIN_COUNT}, 1fr)`, gap: 6, marginBottom: 12 }}>
                {nums.map((v, i) => (
                  <input key={i} id={`wn${i}`} value={v} placeholder="—" maxLength={2}
                    inputMode="numeric"
                    onChange={e => setNum(i, e.target.value)}
                    className="input num-input"
                    style={{ padding: 0, textAlign: 'center', fontSize: 17, fontWeight: 700, height: 44 }}
                  />
                ))}
              </div>

              <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                            textTransform: 'uppercase', marginBottom: 8 }}>
                Bonus number
              </div>
              <input value={bonus} onChange={e => setBonus(e.target.value.replace(/\D/g, '').slice(0, 2))}
                placeholder="—" maxLength={2} inputMode="numeric"
                className="input num-input"
                style={{ width: 56, padding: 0, textAlign: 'center', fontSize: 17, fontWeight: 700,
                         height: 44, marginBottom: 16 }}
              />
            </>
          )}

          <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8, marginTop: hasTickets ? 16 : 0 }}>
            Cash prize (CAD)
          </div>
          <input value={totalPrize} onChange={e => setTotalPrize(e.target.value)}
            placeholder="0.00" type="number" inputMode="decimal" min="0"
            className="input mono" style={{ marginBottom: 16 }}
          />

          <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Free tickets won
          </div>
          <input value={freeTickets} onChange={e => setFreeTickets(e.target.value.replace(/\D/g, ''))}
            placeholder="0" type="number" inputMode="numeric" min="0"
            className="input mono" style={{ marginBottom: 8 }}
          />
          <p style={{ margin: '0 0 16px', fontSize: 13, color: 'var(--tx-3)', lineHeight: 1.5 }}>
            Enter cash and/or free tickets. Free-ticket handling follows your group setting
            (next-round auto-enroll or cash credit from your balance).
          </p>

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

// ── Payment settings (trustee) ─────────────────────────────────────────────
function PaymentsTab({ showToast }) {
  const [group, setGroup] = useState(null)
  const [pm, setPm] = useState('both')
  const [minAmt, setMinAmt] = useState('25')
  const [email, setEmail] = useState('')
  const [freeTicketMode, setFreeTicketMode] = useState('next_round')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.admin.group.get()
      .then(d => {
        const g = d.group
        setGroup(g)
        setPm(g.payment_methods || 'both')
        setMinAmt(String(g.etransfer_min_amount ?? 25))
        setEmail(g.etransfer_email || '')
        setFreeTicketMode(g.free_ticket_mode || 'next_round')
      })
      .catch(err => showToast(err.message, 'error'))
  }, [showToast])

  async function save() {
    setBusy(true)
    try {
      const r = await api.admin.group.patch({
        payment_methods: pm,
        etransfer_min_amount: Number(minAmt) || 25,
        etransfer_email: email.trim() || null,
        free_ticket_mode: freeTicketMode,
      })
      setGroup(r.group)
      showToast('Payment settings saved', 'success')
    } catch (err) { showToast(err.message, 'error') }
    finally { setBusy(false) }
  }

  async function selectFreeTicketMode(mode) {
    setFreeTicketMode(mode)
    setBusy(true)
    try {
      const r = await api.admin.group.patch({ free_ticket_mode: mode })
      setGroup(r.group)
      setFreeTicketMode(r.group.free_ticket_mode || mode)
      showToast(
        mode === 'cash_credit'
          ? 'Free tickets will convert to member credit'
          : 'Free tickets will auto-apply in the next round',
        'success',
      )
    } catch (err) {
      showToast(err.message || 'Could not save setting', 'error')
    } finally {
      setBusy(false)
    }
  }

  if (!group) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
        <div className="spinner" />
      </div>
    )
  }

  const pmOptions = [
    { v: 'both', label: 'Card & e-Transfer' },
    { v: 'card', label: 'Card only' },
    { v: 'etransfer', label: 'E-Transfer only' },
  ]

  const freeTicketOptions = [
    {
      v: 'next_round',
      label: 'Use in next round',
      hint: 'Winners are auto-enrolled in the next round of the same game. All free tickets are applied as shares — no credit charged.',
    },
    {
      v: 'cash_credit',
      label: 'Convert to credit',
      hint: 'Ticket value (by game price) is deducted from your trustee balance and credited to winners by pool share.',
    },
  ]

  return (
    <div style={{ padding: '12px 16px 24px' }}>
      <div className="card col" style={{ gap: 14, marginBottom: 12 }}>
        <FieldLabel label="Accepted payment methods">
          <div className="col" style={{ gap: 8 }}>
            {pmOptions.map(o => (
              <button key={o.v} type="button" onClick={() => setPm(o.v)} style={{
                padding: '12px 14px', borderRadius: 10, cursor: 'pointer', textAlign: 'left',
                border: `.5px solid ${pm === o.v ? 'var(--tg)' : 'var(--hairline-2)'}`,
                background: pm === o.v ? 'rgba(46,166,255,.1)' : 'var(--bg-3)',
                color: pm === o.v ? 'var(--tg)' : '#fff',
                fontFamily: 'inherit', fontSize: 15, fontWeight: 600,
              }}>
                {o.label}
              </button>
            ))}
          </div>
        </FieldLabel>

        {(pm === 'etransfer' || pm === 'both') && (
          <>
            <FieldLabel label="E-transfer deposit email">
              <input className="input mono" type="email" value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="trustee@example.com" />
            </FieldLabel>
            <FieldLabel label="Minimum e-transfer amount (CAD)">
              <input className="input mono" type="number" min="1" step="1"
                value={minAmt} onChange={e => setMinAmt(e.target.value)} />
            </FieldLabel>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-3)', lineHeight: 1.5 }}>
              Members pick $25, $50, $100, or $250 for card. E-transfer options are the same amounts at or above your minimum.
            </p>
          </>
        )}

        {(pm === 'card' || pm === 'both') && !group.stripe_configured && (
          <p style={{ margin: 0, fontSize: 13, color: 'var(--warn)' }}>
            Stripe is not configured on the server — card payments will not work until it is.
          </p>
        )}
      </div>

      <div className="card col" style={{ gap: 14, marginBottom: 12 }}>
        <FieldLabel label="Free ticket prizes">
          <p style={{ margin: '0 0 4px', fontSize: 13, color: 'var(--tx-3)', lineHeight: 1.5 }}>
            Applies to every round in this group when you enter free tickets as a prize.
          </p>
          <div className="col" style={{ gap: 8 }}>
            {freeTicketOptions.map(o => (
              <button key={o.v} type="button" disabled={busy}
                onClick={() => selectFreeTicketMode(o.v)} style={{
                padding: '12px 14px', borderRadius: 10, cursor: 'pointer', textAlign: 'left',
                border: `.5px solid ${freeTicketMode === o.v ? 'var(--gold)' : 'var(--hairline-2)'}`,
                background: freeTicketMode === o.v ? 'rgba(255,193,7,.1)' : 'var(--bg-3)',
                color: freeTicketMode === o.v ? 'var(--gold)' : '#fff',
                fontFamily: 'inherit', fontSize: 15, fontWeight: 600,
              }}>
                <div>{o.label}</div>
                <div style={{ fontSize: 13, fontWeight: 400, color: 'var(--tx-3)', marginTop: 4, lineHeight: 1.45 }}>
                  {o.hint}
                </div>
              </button>
            ))}
          </div>
        </FieldLabel>
      </div>

      <button className="btn btn-primary btn-block" disabled={busy} onClick={() => save()}>
        {busy ? 'Saving…' : 'Save settings'}
      </button>
    </div>
  )
}

// ── Main Admin page ────────────────────────────────────────────────────────
export default function Admin({ user }) {
  const [tab,      setTab]      = useState('round')
  const [rounds,   setRounds]   = useState(undefined)
  const [selectedId, setSelectedId] = useState(null)
  const [deposits, setDeposits] = useState(null)
  const [imapOk,   setImapOk]  = useState(false)
  const [members,  setMembers]  = useState(null)
  const [busy,     setBusy]     = useState({})
  const [showNew,  setShowNew]  = useState(false)
  const [showUp,   setShowUp]   = useState(false)
  const [showRes,  setShowRes]  = useState(false)
  const showToast = useToast()

  const round = rounds?.find(r => r.id === selectedId) ?? rounds?.[0] ?? null

  const [loadError, setLoadError] = useState(null)

  const loadRounds = useCallback(() => api.admin.rounds().then(d => {
    const list = d.rounds || []
    setRounds(list)
    setLoadError(null)
    setSelectedId(prev => {
      if (prev && list.some(r => r.id === prev)) return prev
      return list[0]?.id ?? null
    })
  }).catch(err => {
    setRounds([])
    setLoadError(err.message || 'Could not load rounds')
    showToast(err.message || 'Could not load rounds', 'error')
  }), [showToast])
  const loadDeposits = useCallback(() => api.admin.deposits().then(d => {
    setDeposits(d.deposits)
    setImapOk(!!d.imap_configured)
  }).catch(err => {
    setDeposits([])
    showToast(err.message || 'Could not load deposits', 'error')
  }), [showToast])
  const loadMembers  = useCallback(() => api.admin.members().then(d => setMembers(d.members)).catch(err => {
    setMembers([])
    showToast(err.message || 'Could not load members', 'error')
  }), [showToast])

  useEffect(() => { loadRounds(); loadDeposits(); loadMembers() }, [loadRounds, loadDeposits, loadMembers])

  function setB(k, v) { setBusy(p => ({ ...p, [k]: v })) }

  async function roundAction(key, fn, label) {
    setB(key, true)
    try {
      const res = await fn()
      showToast(label(res), 'success')
      await loadRounds()
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
  const canClose = round && (st === 'open' || ds === 'RALLY' || ds === 'OPEN')
  const canUpload = st === 'closed' || st === 'uploaded' || ds === 'LOCKED' || ds === 'UPLOADED' || ds === 'CLOSING'
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
              <span style={{ fontSize: 16, fontWeight: 600 }}>Your group dashboard</span>
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>
                {user?.group?.name || 'Trustee access'}
                {user?.group?.status === 'suspended' ? ' · suspended' : ''}
              </span>
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
          { Icon: TicketIcon, label: 'Pool',    value: round ? fmtCAD(round.pool) : (rounds?.filter(r => r.status === 'open').length ? `${rounds.filter(r => r.status === 'open').length} live` : '—'), color: 'var(--money)' },
        ].map(({ Icon, label, value, color }) => (
          <div key={label} className="card col gap-4" style={{ padding: '10px 12px' }}>
            <Icon width={14} height={14} style={{ color }} />
            <span className="mono" style={{ fontSize: 17, fontWeight: 700, color }}>{value}</span>
            <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Tab strip */}
      <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8 }}>
        {[
          { id: 'round',    label: 'Round'   },
          { id: 'deposits', label: pendingCount ? `Deposits (${pendingCount})` : 'Deposits' },
          { id: 'members',  label: 'Members' },
          { id: 'payments', label: 'Settings' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{
              flex: 1, padding: '7px 0', borderRadius: 10, border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 600,
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
          {rounds === undefined ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
              <div className="spinner" />
            </div>
          ) : (
            <>
          {loadError && (
            <div className="card" style={{ padding: 12, marginBottom: 12, borderColor: 'var(--danger)' }}>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--danger)' }}>{loadError}</p>
            </div>
          )}
          {rounds.length === 0 && !loadError && (
            <div className="card" style={{ padding: 16, marginBottom: 12, textAlign: 'center' }}>
              <p style={{ margin: '0 0 8px', fontWeight: 600 }}>No rounds yet</p>
              <p style={{ margin: 0, fontSize: 14, color: 'var(--tx-2)' }}>
                Open your first round for this group below.
              </p>
            </div>
          )}
          {rounds.length > 0 && (
            <div style={{ display: 'flex', gap: 8, overflowX: 'auto', marginBottom: 12, paddingBottom: 2 }}>
              {rounds.map(r => {
                const sel = r.id === round?.id
                const meta = lotteryMeta(r.lottery_type)
                return (
                  <button key={r.id} onClick={() => setSelectedId(r.id)} style={{
                    flexShrink: 0, display: 'flex', alignItems: 'center', gap: 6,
                    padding: '8px 12px', borderRadius: 10, cursor: 'pointer', border: 'none',
                    background: sel ? 'rgba(46,166,255,.16)' : 'var(--surface-2)',
                    outline: sel ? '1.5px solid var(--tg)' : '1.5px solid transparent',
                    fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
                    color: sel ? 'var(--tg)' : 'var(--tx-1)',
                  }}>
                    <LotteryLogo type={r.lottery_type} height={18} style={{ width: 28 }} />
                    #{r.group_seq ?? r.id}
                    {r.draw_date && <span style={{ color: 'var(--tx-3)', fontWeight: 500 }}>{r.draw_date.slice(5)}</span>}
                  </button>
                )
              })}
            </div>
          )}
          {round ? (
            <div className="card" style={{ marginBottom: 12 }}>
              <div className="row between" style={{ marginBottom: 12 }}>
                <div className="row gap-8" style={{ alignItems: 'center' }}>
                  <LotteryLogo type={round.lottery_type} height={28} style={{ width: 36 }} />
                  <span style={{ fontSize: 16, fontWeight: 700 }}>Round #{round.group_seq ?? round.id}</span>
                </div>
                <StatusPill status={ds} />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                {[
                  ['Pool',         fmtCAD(round.pool)],
                  ['Participants', round.participants?.length ?? 0],
                  ['Draw date',    round.draw_date ? fmtDate(round.draw_date) : '—'],
                ].map(([k, v]) => (
                  <div key={k} className="col gap-4">
                    <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{k}</span>
                    <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>

              {(round.jackpot_pending && (st === 'open' || st === 'closed')) ? (
                <div style={{ marginBottom: 12 }}>
                  <span style={{
                    display: 'block', fontSize: 12, color: 'var(--tx-3)',
                    textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8,
                  }}>
                    Jackpot
                  </span>
                  <RoundJackpotEditor round={round} onUpdated={loadRounds} showToast={showToast} />
                </div>
              ) : (
                <div className="col gap-4" style={{ marginBottom: 12 }}>
                  <span style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>Jackpot</span>
                  <span className="mono" style={{ fontSize: 14, fontWeight: 600 }}>
                    {round.jackpot ? `$${fmtJackpotCompact(round.jackpot)}` : JACKPOT_PENDING_LABEL}
                  </span>
                </div>
              )}

              {round.participants?.length > 0 && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  {round.participants.map(p => (
                    <div key={p.user_id} style={{ marginBottom: 10 }}>
                      <div className="row between">
                        <span style={{ fontSize: 14, fontWeight: 500 }}>
                          {p.won ? '🏆 ' : ''}{p.full_name}
                        </span>
                        <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>
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
                  <div style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Ticket numbers
                  </div>
                  <TicketNumbersView
                    ticketNumbers={round.ticket_numbers}
                    lotteryType={round.lottery_type}
                  />
                </>
              )}

              {(round.tickets_required > 1 || round.tickets_uploaded > 0) && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  <div style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Tickets · {round.tickets_uploaded ?? 0} / {round.tickets_required ?? 1} uploaded
                  </div>
                </>
              )}
              {(round.round_tickets?.length
                ? round.round_tickets.filter(t => t.image)
                : round.ticket_image ? [{ image: round.ticket_image }] : []
              ).map((t, i) => (
                <img key={i} src={t.image} alt={`Ticket ${i + 1}`}
                  style={{ width: '100%', borderRadius: 10, maxHeight: 180, objectFit: 'cover', marginBottom: 8 }} />
              ))}

              {round.winning_numbers && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  <div style={{ fontSize: 12, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
                    Winning numbers
                  </div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                    {JSON.parse(round.winning_numbers || '[]').map(n => (
                      <span key={n} className="ball md match">{n}</span>
                    ))}
                    {round.bonus_number && (
                      <>
                        <span style={{ color: 'var(--tx-3)', fontSize: 19, fontWeight: 700 }}>+</span>
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
              disabled={busy.new}
              onClick={() => setShowNew(true)}>
              <PlusIcon width={16} height={16} />
              Open new round
            </button>
            {round && (
              <>
                <button className="btn btn-block"
                  style={{ background: 'var(--surface-2)', opacity: canClose ? 1 : .4 }}
                  disabled={!canClose || busy.close}
                  onClick={() => roundAction('close', () => api.admin.closeRound(round.id), () => `Round #${round.group_seq ?? round.id} closed.`)}>
                  {busy.close ? 'Closing…' : `Close round #${round.group_seq ?? round.id}`}
                </button>
                {st === 'open' && (round.participants?.length ?? 0) === 0 && (
                  <button className="btn btn-block"
                    style={{ background: 'rgba(242,107,107,.12)', color: 'var(--danger)' }}
                    disabled={busy.delete}
                    onClick={() => {
                      if (!window.confirm(`Delete round #${round.group_seq ?? round.id}? This can't be undone.`)) return
                      roundAction('delete',
                        () => api.admin.deleteRound(round.id),
                        () => `Round #${round.group_seq ?? round.id} deleted.`)
                        .then(() => setSelectedId(null))
                    }}>
                    {busy.delete ? 'Deleting…' : `Delete round #${round.group_seq ?? round.id}`}
                  </button>
                )}
                <button className="btn btn-block"
                  style={{ background: canUpload ? 'rgba(46,166,255,.12)' : 'var(--surface-2)',
                           color: canUpload ? 'var(--tg)' : undefined, opacity: canUpload ? 1 : .4 }}
                  disabled={!canUpload}
                  onClick={() => setShowUp(true)}>
                  <CameraIcon width={16} height={16} />
                  Scan tickets
                  {round.tickets_required > 1 && (
                    <span style={{ fontSize: 12, opacity: 0.85 }}>
                      {' '}({round.tickets_uploaded ?? 0}/{round.tickets_required})
                    </span>
                  )}
                </button>
                <button className="btn btn-block"
                  style={{ background: canResults ? 'rgba(245,199,59,.12)' : 'var(--surface-2)',
                           color: canResults ? 'var(--gold)' : undefined, opacity: canResults ? 1 : .4 }}
                  disabled={!canResults}
                  onClick={() => setShowRes(true)}>
                  <TrophyIcon width={16} height={16} />
                  Enter results
                </button>
              </>
            )}
          </div>
            </>
          )}
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
                    fontSize: 15, fontWeight: 700, color: 'var(--tg)', flexShrink: 0,
                  }}>
                    {(d.full_name || '?')[0].toUpperCase()}
                  </div>
                  <div className="col gap-4">
                    <span style={{ fontWeight: 600, fontSize: 15 }}>{d.full_name}</span>
                    {d.username && <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>@{d.username}</span>}
                    {d.ref_code && (
                      <span style={{ fontSize: 12, color: 'var(--tg)', fontFamily: 'var(--mono)', fontWeight: 600 }}>
                        {d.ref_code}
                      </span>
                    )}
                  </div>
                </div>
                <div className="col" style={{ textAlign: 'right', gap: 2 }}>
                  <span className="mono" style={{ fontSize: 19, fontWeight: 700, color: 'var(--money)' }}>
                    {fmtCAD(d.amount)}
                  </span>
                  <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>
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

      {tab === 'payments' && (
        <PaymentsTab showToast={showToast} />
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
                  <TelegramAvatar
                    user={m}
                    size={36}
                    style={m.is_group_trustee ? { boxShadow: '0 0 0 2px var(--gold)' } : undefined}
                  />
                  <div className="col grow gap-4" style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 500, fontSize: 15 }}>
                      {m.full_name}
                      {m.is_group_trustee && (
                        <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--gold)', fontWeight: 700 }}>TRUSTEE</span>
                      )}
                    </span>
                    {m.username && <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>@{m.username}</span>}
                  </div>
                  <div className="col" style={{ textAlign: 'right', gap: 2, flexShrink: 0 }}>
                    <span className="mono" style={{ fontSize: 15, fontWeight: 700 }}>{fmtCAD(m.credit)}</span>
                    <span style={{ fontSize: 12, color: 'var(--tx-3)' }}>balance</span>
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
          onCreated={(id) => loadRounds().then(() => id && setSelectedId(id))}
          showToast={showToast}
        />
      )}
      {showUp && round && (
        <UploadTicketSheet
          round={round}
          onClose={() => setShowUp(false)}
          onUploaded={loadRounds}
          showToast={showToast}
        />
      )}
      {showRes && round && (
        <ResultsSheet
          round={round}
          onClose={() => setShowRes(false)}
          onResults={loadRounds}
          showToast={showToast}
        />
      )}
    </div>
  )
}
