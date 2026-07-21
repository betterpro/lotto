import { useState, useEffect, useCallback, useRef } from 'react'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, PaymentElement, useStripe, useElements } from '@stripe/react-stripe-js'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { StatusPill } from '../components/StatusPill.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'
import {
  LOTTERY_TYPES, lotteryMeta, ticketLayout, emptyTicketRows,
  parseTicketNumbers, ticketRowsValid, ticketRowsToNumbers, mergeScannedRows,
  isVariableRowLayout, rowSpecForIndex, addTicketRow, removeTicketRow,
  JACKPOT_PENDING_LABEL, fmtJackpotCompact,
  rowsPerTicket, countTickets, groupRowsIntoTickets,
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
  const rpt = rowsPerTicket(round?.lottery_type)
  const required = round?.tickets_required ?? 1
  const savedTickets = (round?.round_tickets || []).filter(t => t?.rows?.length)
  const alreadySaved = savedTickets.length
  const savedRows = savedTickets.reduce((a, t) => a + (t.rows?.length || 0), 0)
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
  // Count whole tickets by printed lines (Lotto Max = 3 lines/ticket), not photos.
  const readyRows = readyTickets.reduce((a, t) => a + (t.rows?.length || 0), 0)
  const totalAfterSave = countTickets(savedRows + readyRows, round?.lottery_type)
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
      if (totalAfterSave >= required) {
        await api.admin.uploadTicket(round.id)
        showToast(`All ${required} ticket${required === 1 ? '' : 's'} uploaded!`, 'success')
      } else {
        showToast(`Saved ${totalAfterSave} of ${required} — scan ${required - totalAfterSave} more`, 'info')
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
            {rpt > 1 && ` · each ${layout.repeatRow ? 'ticket' : 'play'} = ${rpt} lines — a photo can hold several tickets`}
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

// ── Enter Results Sheet ───────────────────────────────────────────────────
function resultTicketRows(round) {
  // Prefer the finalized ticket_numbers; fall back to the scanned tickets'
  // rows (round_tickets) so results still show the fetched numbers even if the
  // trustee hasn't run the final "Save & notify" upload step yet.
  const fromNumbers = parseTicketNumbers(round?.ticket_numbers)
  if (fromNumbers.length) return fromNumbers
  const saved = Array.isArray(round?.round_tickets) ? round.round_tickets : []
  return saved
    .flatMap(t => (Array.isArray(t?.rows) ? t.rows : []))
    .filter(r => Array.isArray(r) && r.length)
    .map(r => r.map(String))
}

function ResultsSheet({ round, onClose, onResults, showToast }) {
  const ticketRows = resultTicketRows(round)
  const hasTickets = ticketRows.length > 0
  const ticketGroups = groupRowsIntoTickets(ticketRows, round?.lottery_type)
  // Winning main-number count varies by game: Lotto Max 7, 6/49 6, Daily Grand 5.
  const rLayout = ticketLayout(round?.lottery_type)
  const mainCount = isVariableRowLayout(rLayout) ? rLayout.repeatRow.count : (rLayout.rows[0]?.count ?? 7)

  const [mainNums,   setMainNums]   = useState([])
  const [nums,       setNums]       = useState(() => Array(mainCount).fill(''))
  const [bonus,      setBonus]      = useState('')
  const [pickBonus,  setPickBonus]  = useState(false)
  const [totalPrize, setTotalPrize] = useState('')
  const [freeTickets, setFreeTickets] = useState('')
  // Per-ticket outcome: 'none' (no win), 'free' (free ticket(s)), or 'cash' ($).
  const [perTicket, setPerTicket] = useState(
    () => ticketGroups.map(() => ({ outcome: 'none', prize: '', free: '1' })),
  )
  const [busy,       setBusy]       = useState(false)
  const [autoBusy,   setAutoBusy]   = useState(false)
  const [autoTickets, setAutoTickets] = useState(null)  // per-ticket detected line tiers
  const [autoInfo,   setAutoInfo]   = useState(null)     // {draw_date, has_variable, ...}

  async function runAutoCalc() {
    setAutoBusy(true)
    try {
      const d = await api.admin.autoResults(round.id)
      const wn = (d.winning_numbers || []).map(Number)
      setMainNums(wn)
      if (d.bonus_number != null) setBonus(String(d.bonus_number))
      const per = (d.tickets || []).map(t => {
        if (t.cash > 0) return { outcome: 'cash', prize: String(t.cash), free: String(t.free || 1) }
        if (t.free > 0) return { outcome: 'free', prize: '', free: String(t.free) }
        if (t.has_variable) return { outcome: 'cash', prize: '', free: '1' }  // enter amount
        return { outcome: 'none', prize: '', free: '1' }
      })
      if (per.length) setPerTicket(per)
      setAutoTickets(d.tickets || [])
      setAutoInfo({ draw_date: d.draw_date, has_variable: d.has_variable,
                    total_cash: d.total_cash, total_free: d.total_free })
      showToast(
        d.has_variable
          ? 'Auto-calculated — enter the amounts marked “varies”, then review'
          : 'Auto-calculated — review and accept',
        d.has_variable ? 'info' : 'success',
      )
    } catch (err) {
      showToast(err.message, 'error')
    } finally { setAutoBusy(false) }
  }

  function setTicketField(i, key, v) {
    setPerTicket(prev => prev.map((t, j) => j === i ? { ...t, [key]: v } : t))
  }
  function setTicketOutcome(i, outcome) {
    setPerTicket(prev => prev.map((t, j) => j === i ? { ...t, outcome } : t))
  }
  function bumpFree(i, delta) {
    setPerTicket(prev => prev.map((t, j) =>
      j === i ? { ...t, free: String(Math.max(1, (Number(t.free) || 1) + delta)) } : t))
  }

  function setNum(i, v) {
    const c = [...nums]
    c[i] = v.replace(/\D/g, '').slice(0, 2)
    setNums(c)
    if (v.length >= 2 && i < mainCount - 1) {
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
    if (mainNums.length < mainCount) {
      setMainNums(prev => [...prev, v])
    }
  }

  function clearBonus() {
    setBonus('')
    setPickBonus(false)
  }

  const winningNumbers = hasTickets ? mainNums : nums.map(Number)
  const mainSet = new Set(mainNums.map(Number))
  const bonusN = bonus ? Number(bonus) : null

  // Each ticket contributes its cash amount (outcome 'cash') or free tickets
  // (outcome 'free'); 'none' contributes nothing. Totals roll up the round result.
  const ticketCash = t => (t.outcome === 'cash' ? (Number(t.prize) || 0) : 0)
  const ticketFree = t => (t.outcome === 'free' ? Math.max(1, Number(t.free) || 1) : 0)
  const perTicketTotal = perTicket.reduce((a, t) => a + ticketCash(t), 0)
  const perTicketFree  = perTicket.reduce((a, t) => a + ticketFree(t), 0)
  const winningTicketCount = perTicket.filter(t => t.outcome !== 'none').length
  const cashPrize = hasTickets ? perTicketTotal : (totalPrize === '' ? 0 : Number(totalPrize))
  const freeTicketCount = hasTickets ? perTicketFree : (freeTickets === '' ? 0 : Number(freeTickets))
  const numbersReady = hasTickets
    ? mainNums.length === mainCount
    : nums.every(n => n && Number(n) >= 1)
  const valid = numbersReady && bonus && Number(bonus) >= 1 &&
    cashPrize >= 0 && freeTicketCount >= 0 &&
    // Per-ticket flow can finalize a losing round (all "No win"); the legacy
    // whole-round entry still requires a cash or free-ticket prize.
    (hasTickets || cashPrize > 0 || freeTicketCount > 0)

  async function submit() {
    setBusy(true)
    try {
      const opts = hasTickets
        ? { tickets: perTicket.map(t => ({ prize: ticketCash(t), free: ticketFree(t) })) }
        : { total_prize: cashPrize, free_tickets: freeTicketCount }
      await api.admin.results(round.id, winningNumbers, Number(bonus), opts)
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
          <p style={{ fontSize: 14, color: 'var(--tx-2)', marginBottom: 12, lineHeight: 1.5 }}>
            {hasTickets
              ? 'Auto-calculate from the official results, or set the winning numbers and each ticket’s result yourself. Review before you accept — the total is shared out to participants by their pool stake.'
              : `Enter the ${mainCount} winning numbers and bonus. Prize allocation is computed automatically and distributed to participants proportionally.`}
          </p>

          {hasTickets && (
            <button type="button" className="btn btn-block"
              disabled={autoBusy}
              onClick={runAutoCalc}
              style={{ marginBottom: 14, gap: 8, background: 'rgba(46,166,255,.14)',
                color: 'var(--tg)', border: '.5px solid rgba(46,166,255,.3)', fontWeight: 700 }}>
              {autoBusy ? 'Fetching official results…' : '🔮 Auto-calculate from official results'}
            </button>
          )}

          {autoInfo && (
            <div style={{ fontSize: 13, borderRadius: 10, padding: '10px 12px', marginBottom: 14,
              lineHeight: 1.5, background: 'rgba(78,208,122,.1)', color: 'var(--money)',
              border: '.5px solid rgba(78,208,122,.3)' }}>
              ✅ Calculated from the official {autoInfo.draw_date || 'draw'} results — each ticket below is
              pre-filled. Please review, adjust if needed, then accept.
              {autoInfo.has_variable && (
                <div style={{ color: 'var(--warn)', marginTop: 6 }}>
                  ⚠ Some tickets hit a top tier whose amount <b>varies per draw</b> — enter that amount
                  from the official prize breakdown before accepting.
                </div>
              )}
            </div>
          )}

          <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Winning numbers
          </div>

          {hasTickets ? (
            <>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8 }}>
                {Array.from({ length: mainCount }, (_, i) => {
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
                ticketNumbers={ticketRows}
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
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${mainCount}, 1fr)`, gap: 6, marginBottom: 12 }}>
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

          {hasTickets ? (
            <>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                            textTransform: 'uppercase', marginBottom: 4, marginTop: 16 }}>
                Prize per ticket
              </div>
              <p style={{ margin: '0 0 12px', fontSize: 13, color: 'var(--tx-3)', lineHeight: 1.5 }}>
                For each ticket, tap its result — <b>No win</b>, <b>Free ticket</b>, or a cash
                <b> Amount</b>. Set the winning numbers above to see which lines matched. The round
                total adds up automatically.
              </p>

              <div className="col" style={{ gap: 10, marginBottom: 14 }}>
                {ticketGroups.map((grp, ti) => {
                  const t = perTicket[ti] || { outcome: 'none', prize: '', free: '1' }
                  const best = numbersReady
                    ? Math.max(0, ...grp.map(row => row.filter(n => mainSet.has(Number(n))).length))
                    : null
                  const won = t.outcome !== 'none'
                  const OPTS = [
                    { v: 'none', label: 'No win' },
                    { v: 'free', label: '🎁 Free' },
                    { v: 'cash', label: '💵 Amount' },
                  ]
                  return (
                    <div key={ti} className="card" style={{ padding: 10,
                      border: `.5px solid ${won ? 'rgba(245,199,59,.5)' : 'var(--hairline)'}` }}>
                      <div className="row between" style={{ alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 700 }}>Ticket {ti + 1}</span>
                        {numbersReady && (
                          <span style={{ fontSize: 12, color: best > 0 ? 'var(--money)' : 'var(--tx-3)', fontWeight: 600 }}>
                            best {best}/{mainCount}
                          </span>
                        )}
                      </div>
                      <div className="col" style={{ gap: 6, marginBottom: 10 }}>
                        {grp.map((row, ri) => {
                          const li = autoTickets?.[ti]?.lines?.[ri]
                          const tierText = li?.win
                            ? (li.variable ? `${li.tier} · varies`
                               : li.free ? `${li.tier} · free play`
                               : `${li.tier} · $${Number(li.amount).toFixed(2)}`)
                            : (li ? 'no win' : null)
                          return (
                            <div key={ri} style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center' }}>
                              {row.map((n, ni) => {
                                const v = Number(n)
                                const cls = mainSet.has(v) ? 'match' : (bonusN === v ? 'bonus' : 'white')
                                return <span key={ni} className={`ball sm ${cls}`}>{n}</span>
                              })}
                              {tierText && (
                                <span style={{ fontSize: 11, fontWeight: 700, marginLeft: 4,
                                  color: li.win ? (li.variable ? 'var(--warn)' : 'var(--money)') : 'var(--tx-3)' }}>
                                  {tierText}
                                </span>
                              )}
                            </div>
                          )
                        })}
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                        {OPTS.map(o => (
                          <button key={o.v} type="button" onClick={() => setTicketOutcome(ti, o.v)}
                            style={{
                              padding: '9px 4px', borderRadius: 9, cursor: 'pointer',
                              fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                              border: `.5px solid ${t.outcome === o.v
                                ? (o.v === 'none' ? 'var(--hairline-2)' : 'var(--gold)') : 'var(--hairline-2)'}`,
                              background: t.outcome === o.v
                                ? (o.v === 'none' ? 'var(--bg-3)' : 'rgba(245,199,59,.14)') : 'var(--bg-3)',
                              color: t.outcome === o.v
                                ? (o.v === 'none' ? 'var(--tx-1)' : 'var(--gold)') : 'var(--tx-3)',
                            }}>
                            {o.label}
                          </button>
                        ))}
                      </div>

                      {t.outcome === 'cash' && (
                        <div className="row gap-8" style={{ marginTop: 10, alignItems: 'center' }}>
                          <span style={{ fontSize: 16, fontWeight: 700, color: 'var(--tx-2)' }}>$</span>
                          <input value={t.prize} onChange={e => setTicketField(ti, 'prize', e.target.value)}
                            placeholder="0.00" type="number" inputMode="decimal" min="0" autoFocus
                            className="input mono" style={{ flex: 1 }} />
                          <span style={{ fontSize: 13, color: 'var(--tx-3)' }}>CAD</span>
                        </div>
                      )}
                      {t.outcome === 'free' && (
                        <div className="row between" style={{ marginTop: 10, alignItems: 'center' }}>
                          <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Free tickets won</span>
                          <div className="row gap-8" style={{ alignItems: 'center' }}>
                            <button type="button" onClick={() => bumpFree(ti, -1)}
                              className="btn" style={{ width: 34, height: 34, padding: 0, background: 'var(--surface-2)' }}>−</button>
                            <span className="mono" style={{ fontSize: 16, fontWeight: 700, minWidth: 20, textAlign: 'center' }}>
                              {Math.max(1, Number(t.free) || 1)}
                            </span>
                            <button type="button" onClick={() => bumpFree(ti, 1)}
                              className="btn" style={{ width: 34, height: 34, padding: 0, background: 'var(--surface-2)' }}>+</button>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              <div className="card" style={{ marginBottom: 16,
                border: (perTicketTotal > 0 || perTicketFree > 0) ? '.5px solid rgba(245,199,59,.4)' : undefined }}>
                <div style={{ fontSize: 12, color: 'var(--tx-3)', fontWeight: 600, letterSpacing: '.3px',
                  textTransform: 'uppercase', marginBottom: 4 }}>Round result</div>
                <SummaryRow k="Winning tickets"    v={`${winningTicketCount} of ${ticketGroups.length}`} mono />
                <SummaryRow k="Total cash prize"   v={fmtCAD(perTicketTotal)} mono />
                <SummaryRow k="Total free tickets" v={perTicketFree} mono />
                <SummaryRow k="Pool total"         v={fmtCAD(round?.pool)} mono />
                <SummaryRow k="Participants"       v={round?.participants?.length ?? 0} mono />
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                            textTransform: 'uppercase', marginBottom: 8 }}>
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
                <SummaryRow k="Round"        v={`#${round?.group_seq ?? round?.id}`} mono />
                <SummaryRow k="Pool total"   v={fmtCAD(round?.pool)} mono />
                <SummaryRow k="Participants" v={round?.participants?.length ?? 0} mono />
              </div>
            </>
          )}

          <button className="btn btn-primary btn-block" disabled={!valid || busy} onClick={submit}>
            <TrophyIcon width={16} height={16} />
            {busy ? 'Processing…' : 'Stage results & distribute'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Group platform subscription ($6.99/mo, billed by the platform) ──────────
function SubPayForm({ onSuccess, onError }) {
  const stripe = useStripe(), elements = useElements()
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    if (!stripe || !elements) return
    setBusy(true)
    const { error } = await stripe.confirmPayment({
      elements, confirmParams: { return_url: window.location.origin }, redirect: 'if_required',
    })
    setBusy(false)
    if (error) onError(error.message); else onSuccess()
  }
  return (
    <form onSubmit={submit}>
      <PaymentElement options={{ layout: 'tabs' }} />
      <button type="submit" className="btn btn-primary btn-block" style={{ marginTop: 12 }} disabled={busy || !stripe}>
        {busy ? 'Processing…' : 'Start subscription · $6.99/mo'}
      </button>
    </form>
  )
}

function GroupSubscriptionCard({ showToast, onChange }) {
  const [sub, setSub] = useState(null)
  const [pk, setPk] = useState(null)
  const [cs, setCs] = useState(null)
  const [sp, setSp] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => api.admin.group.subscription().then(setSub).catch(() => {}), [])
  useEffect(() => {
    load()
    api.stripe.config().then(c => setPk(c.publishable_key)).catch(() => {})
  }, [load])

  if (!sub || !sub.required) return null
  const active = sub.status === 'active'

  async function subscribe() {
    setBusy(true)
    try {
      const r = await api.admin.group.subscriptionCreate()
      if (!pk) { showToast('Card payment is unavailable right now', 'error'); return }
      setSp(loadStripe(pk)); setCs(r.client_secret)
    } catch (e) { showToast(e.message, 'error') } finally { setBusy(false) }
  }
  async function cancel() {
    if (!window.confirm('Cancel the group subscription? Your group will be locked immediately and you won’t be able to access it until you reactivate.')) return
    setBusy(true)
    try {
      await api.admin.group.subscriptionCancel()
      showToast('Subscription cancelled — group locked', 'info')
      onChange?.()
    } catch (e) { showToast(e.message, 'error') } finally { setBusy(false) }
  }

  if (cs && sp) return (
    <div className="card col" style={{ gap: 12, marginBottom: 12 }}>
      <span style={{ fontSize: 15, fontWeight: 700 }}>Group subscription · $6.99/mo</span>
      <Elements stripe={sp} options={{ clientSecret: cs, appearance: { theme: 'night' } }}>
        <SubPayForm
          onSuccess={() => { setCs(null); showToast('Subscription started', 'success'); setTimeout(() => { load(); onChange?.() }, 3000) }}
          onError={m => showToast(m, 'error')}
        />
      </Elements>
    </div>
  )

  return (
    <div className="card col" style={{ gap: 10, marginBottom: 12 }}>
      <div className="row between" style={{ alignItems: 'center' }}>
        <span style={{ fontSize: 15, fontWeight: 700 }}>Group subscription</span>
        <span style={{ fontSize: 12, fontWeight: 700, color: active ? 'var(--money)' : 'var(--warn)' }}>
          {active ? 'Active' : 'Inactive'}
        </span>
      </div>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.55 }}>
        Your group runs on the <strong>$6.99/month</strong> plan, billed to your card by LottoChee.
        {active && sub.next_billing ? ` Next charge ${sub.next_billing}.` : ''}
      </p>
      {active ? (
        <button type="button" className="btn btn-block" style={{ background: 'var(--surface-2)', color: 'var(--danger)' }}
          disabled={busy} onClick={cancel}>
          {busy ? 'Working…' : 'Cancel subscription'}
        </button>
      ) : (
        <button type="button" className="btn btn-primary btn-block" disabled={busy} onClick={subscribe}>
          {busy ? 'Working…' : 'Subscribe · $6.99/mo'}
        </button>
      )}
      {active && (
        <p style={{ margin: 0, fontSize: 11, color: 'var(--tx-3)', lineHeight: 1.5 }}>
          Cancelling locks the group immediately — you won’t be able to access it until you reactivate.
        </p>
      )}
    </div>
  )
}

// ── Locked-group screen (subscription cancelled) ────────────────────────────
function LockedAdmin({ showToast, onReactivated }) {
  return (
    <div className="tab-content">
      <div style={{ padding: '40px 20px', maxWidth: 460, margin: '0 auto', textAlign: 'center' }}>
        <div style={{ fontSize: 44, marginBottom: 8 }}>🔒</div>
        <h2 style={{ fontSize: 19, fontWeight: 800, margin: '0 0 8px' }}>Group locked</h2>
        <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, margin: '0 0 20px' }}>
          The group subscription was cancelled, so this group and its data are locked.
          Reactivate the $6.99/month subscription to unlock it for you and your members.
        </p>
        <div style={{ textAlign: 'left' }}>
          <GroupSubscriptionCard showToast={showToast} onChange={onReactivated} />
        </div>
      </div>
    </div>
  )
}

// ── Payment settings (trustee) ─────────────────────────────────────────────
function PaymentsTab({ showToast, onGroupChange }) {
  const [group, setGroup] = useState(null)
  const [pm, setPm] = useState('both')
  const [minAmt, setMinAmt] = useState('25')
  const [email, setEmail] = useState('')
  const [freeTicketMode, setFreeTicketMode] = useState('next_round')
  const [rem1, setRem1] = useState('48')
  const [rem2, setRem2] = useState('24')
  const [busy, setBusy] = useState(false)
  const [stripe, setStripe] = useState(null)   // { connected, charges_enabled, ... }
  const [bcast, setBcast] = useState('')
  const [bcastBusy, setBcastBusy] = useState(false)

  async function sendBroadcast() {
    const msg = bcast.trim()
    if (!msg) return
    if (!window.confirm('Send this message to all members of your group?')) return
    setBcastBusy(true)
    try {
      const r = await api.admin.broadcast(msg)
      showToast(`Sent to ${r.sent} member${r.sent === 1 ? '' : 's'}`, 'success')
      setBcast('')
    } catch (e) { showToast(e.message, 'error') } finally { setBcastBusy(false) }
  }
  const [stripeBusy, setStripeBusy] = useState(false)

  const loadStripeStatus = useCallback(() => {
    api.admin.group.stripeStatus().then(setStripe).catch(() => {})
  }, [])
  useEffect(() => { loadStripeStatus() }, [loadStripeStatus])

  async function connectStripe() {
    setStripeBusy(true)
    try {
      const r = await api.admin.group.stripeConnect()
      if (r.url) {
        const tg = window.Telegram?.WebApp
        if (tg?.openLink) tg.openLink(r.url)
        else window.location.href = r.url
      }
    } catch (e) { showToast(e.message, 'error') }
    finally { setStripeBusy(false) }
  }

  useEffect(() => {
    api.admin.group.get()
      .then(d => {
        const g = d.group
        setGroup(g)
        setPm(g.payment_methods || 'both')
        setMinAmt(String(g.etransfer_min_amount ?? 25))
        setEmail(g.etransfer_email || '')
        setFreeTicketMode(g.free_ticket_mode || 'next_round')
        setRem1(String(g.reminder_hours_1 ?? 48))
        setRem2(String(g.reminder_hours_2 ?? 24))
      })
      .catch(err => showToast(err.message, 'error'))
  }, [showToast])

  async function save() {
    setBusy(true)
    try {
      const h1 = Math.max(1, Math.min(336, parseInt(rem1, 10) || 48))
      const h2 = Math.max(1, Math.min(336, parseInt(rem2, 10) || 24))
      const r = await api.admin.group.patch({
        payment_methods: pm,
        etransfer_min_amount: Number(minAmt) || 25,
        etransfer_email: email.trim() || null,
        free_ticket_mode: freeTicketMode,
        reminder_hours_1: h1,
        reminder_hours_2: h2,
      })
      setGroup(r.group)
      setRem1(String(r.group.reminder_hours_1 ?? h1))
      setRem2(String(r.group.reminder_hours_2 ?? h2))
      showToast('Settings saved', 'success')
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

  const isPrizeShare = group.pricing_plan === 'prize_share'

  return (
    <div style={{ padding: '12px 16px 24px' }}>
      <div className="card" style={{ marginBottom: 12, padding: 14 }}>
        <div style={{ fontSize: 11, color: 'var(--tx-3)', fontWeight: 600, textTransform: 'uppercase',
          letterSpacing: '.4px', marginBottom: 6 }}>Group plan · locked</div>
        <div className="row between" style={{ alignItems: 'center' }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>
            {isPrizeShare ? 'Big-prize share' : 'Monthly subscription'}
          </span>
          <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--money)' }}>
            {isPrizeShare ? 'No monthly fee' : '$6.99/mo'}
          </span>
        </div>
        <p style={{ fontSize: 12, color: 'var(--tx-2)', margin: '6px 0 0', lineHeight: 1.5 }}>
          {isPrizeShare
            ? 'No monthly fee. The platform may claim 5% of any prize over $1,000, as set out in the group agreement.'
            : 'A $6.99/month flat fee. The platform takes no share of any prize.'}
          {' '}This plan was chosen when the group was created and can’t be changed.
        </p>
      </div>

      <GroupSubscriptionCard showToast={showToast} onChange={onGroupChange} />

      <div className="card col" style={{ gap: 10, marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Message your members</div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.5 }}>
          Send a one-off announcement to everyone in your group on Telegram.
        </p>
        <textarea className="input" rows={3} maxLength={2000}
          placeholder="e.g. New round is up — join before Friday's draw! 🎉"
          value={bcast} onChange={e => setBcast(e.target.value)}
          style={{ resize: 'vertical', lineHeight: 1.5 }} />
        <button type="button" className="btn btn-primary btn-block"
          disabled={bcastBusy || !bcast.trim()} onClick={sendBroadcast}>
          {bcastBusy ? 'Sending…' : '📢 Send to all members'}
        </button>
      </div>

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

      {(pm === 'card' || pm === 'both') && group.stripe_configured && (() => {
        const connected = stripe?.connected
        const ready = stripe?.charges_enabled
        const statusLabel = !connected ? 'Not connected'
          : ready ? 'Connected · ready' : 'Setup incomplete'
        const statusColor = ready ? 'var(--money)' : connected ? 'var(--warn)' : 'var(--tx-3)'
        return (
          <div className="card col" style={{ gap: 12, marginBottom: 12 }}>
            <div className="row between" style={{ alignItems: 'center' }}>
              <span style={{ fontSize: 15, fontWeight: 700 }}>Card payments · Stripe</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: statusColor }}>{statusLabel}</span>
            </div>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.55 }}>
              Connect your own Stripe account to accept card top-ups. Members’ payments — and the
              Stripe processing fees — go directly to your Stripe account; the platform takes no cut.
            </p>
            <button type="button" className="btn btn-primary btn-block"
              disabled={stripeBusy} onClick={connectStripe}>
              {stripeBusy ? 'Opening Stripe…'
                : !connected ? 'Connect Stripe account'
                : ready ? 'Manage / update Stripe' : 'Finish Stripe setup'}
            </button>
            {connected && !ready && (
              <button type="button" className="btn btn-block" style={{ background: 'var(--surface-2)' }}
                onClick={loadStripeStatus}>Refresh status</button>
            )}
            {!ready && (
              <p style={{ margin: 0, fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
                Card top-up stays hidden for members until your Stripe account is connected and able to accept charges.
              </p>
            )}
          </div>
        )
      })()}

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

      <div className="card col" style={{ gap: 12, marginBottom: 12 }}>
        <div style={{ fontSize: 15, fontWeight: 700 }}>Closing-soon reminders</div>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.5 }}>
          Members who haven’t joined an open round get a nudge on Telegram before entries close.
          Set how many hours before the draw each reminder is sent.
        </p>
        <div className="row gap-8">
          <FieldLabel label="First reminder (hours before)">
            <input className="input mono" type="number" min="1" max="336" step="1"
              value={rem1} onChange={e => setRem1(e.target.value)} />
          </FieldLabel>
          <FieldLabel label="Second reminder (hours before)">
            <input className="input mono" type="number" min="1" max="336" step="1"
              value={rem2} onChange={e => setRem2(e.target.value)} />
          </FieldLabel>
        </div>
        <p style={{ margin: 0, fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
          Tip: set the first reminder earlier than the second (e.g. 48 and 24). Each member gets each reminder once.
        </p>
      </div>

      <button className="btn btn-primary btn-block" disabled={busy} onClick={() => save()}>
        {busy ? 'Saving…' : 'Save settings'}
      </button>

    </div>
  )
}

// ── Main Admin page ────────────────────────────────────────────────────────
const EMPTY_NOTIFICATION_RULE = {
  name: 'Low credit reminder',
  trigger_type: 'condition',
  event_key: 'new_round',
  condition_field: 'credit',
  operator: 'lt',
  threshold: '5',
  message: 'Hi {name}, your credit is ${credit}. Please increase your credit.',
  text_direction: 'auto',
  language: 'en',
  enabled: true,
}

const NOTIFICATION_OPERATOR_LABELS = {
  lt: 'is less than',
  lte: 'is at most',
  gt: 'is greater than',
  gte: 'is at least',
}

const NOTIFICATION_FORMATS = [
  { tag: 'b', label: 'B', title: 'Bold', sample: 'bold text' },
  { tag: 'i', label: 'I', title: 'Italic', sample: 'italic text' },
  { tag: 'u', label: 'U', title: 'Underline', sample: 'underlined text' },
  { tag: 's', label: 'S', title: 'Strikethrough', sample: 'strikethrough text' },
  { tag: 'code', label: '</>', title: 'Code', sample: 'code' },
  { tag: 'tg-spoiler', label: 'Spoiler', title: 'Spoiler', sample: 'hidden text' },
  { tag: 'blockquote', label: 'Quote', title: 'Quote', sample: 'quoted text' },
]

const NOTIFICATION_LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'fa', label: 'فارسی' },
  { value: 'fr', label: 'Français' },
]
const NOTIFICATION_AI_TONES = [
  { value: 'friendly', label: 'Friendly' },
  { value: 'fun', label: 'Fun' },
  { value: 'professional', label: 'Professional' },
  { value: 'urgent', label: 'Urgent' },
]
const NOTIFICATION_AI_LENGTHS = [
  { value: 'short', label: 'Short' },
  { value: 'standard', label: 'Standard' },
  { value: 'detailed', label: 'Detailed' },
]

const TELEGRAM_EDITOR_TAGS = new Set([
  'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
  'code', 'pre', 'blockquote', 'tg-spoiler', 'br',
])
const TELEGRAM_TAG_MAP = {
  strong: 'b', em: 'i', ins: 'u', strike: 's', del: 's',
}

function escapeEditorText(text) {
  return text.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}

function serializeTelegramNode(node) {
  if (node.nodeType === Node.TEXT_NODE) return escapeEditorText(node.nodeValue || '')
  if (node.nodeType !== Node.ELEMENT_NODE) return ''
  const sourceTag = node.tagName.toLowerCase()
  const children = [...node.childNodes].map(serializeTelegramNode).join('')
  if (sourceTag === 'br') return '\n'
  if (sourceTag === 'div' || sourceTag === 'p') return `${children}\n`
  const tag = TELEGRAM_TAG_MAP[sourceTag] || sourceTag
  if (!TELEGRAM_EDITOR_TAGS.has(sourceTag)) return children
  return `<${tag}>${children}</${tag}>`
}

function serializeTelegramEditor(editor) {
  return [...editor.childNodes].map(serializeTelegramNode).join('')
    .replace(/\n{3,}/g, '\n\n').replace(/\n+$/g, '')
}

function safeTelegramEditorHtml(value) {
  if (typeof document === 'undefined') return ''
  const template = document.createElement('template')
  template.innerHTML = value || ''
  for (const element of [...template.content.querySelectorAll('*')]) {
    const tag = element.tagName.toLowerCase()
    if (!TELEGRAM_EDITOR_TAGS.has(tag)) {
      element.replaceWith(document.createTextNode(element.textContent || ''))
      continue
    }
    for (const attr of [...element.attributes]) element.removeAttribute(attr.name)
  }
  return template.innerHTML
}

function FormattedNotificationText({ value, direction = 'auto' }) {
  return <div dir={direction === 'auto' ? 'auto' : direction}
    dangerouslySetInnerHTML={{ __html: safeTelegramEditorHtml(value) }} />
}

function NotificationMessageEditor({ value, onChange, direction, onDirectionChange, placeholders, placeholderHelp = {} }) {
  const editorRef = useRef(null)
  const selectionRef = useRef(null)

  useEffect(() => {
    const editor = editorRef.current
    if (!editor || document.activeElement === editor) return
    const safe = safeTelegramEditorHtml(value)
    if (editor.innerHTML !== safe) editor.innerHTML = safe
  }, [value])

  function saveSelection() {
    const editor = editorRef.current
    const selection = window.getSelection()
    if (!editor || !selection?.rangeCount) return
    const range = selection.getRangeAt(0)
    if (editor.contains(range.commonAncestorContainer)) selectionRef.current = range.cloneRange()
  }

  function activeRange() {
    const editor = editorRef.current
    if (!editor) return null
    const selection = window.getSelection()
    let range = selectionRef.current?.cloneRange()
    if (!range || !editor.contains(range.commonAncestorContainer)) {
      range = document.createRange()
      range.selectNodeContents(editor)
      range.collapse(false)
    }
    selection.removeAllRanges()
    selection.addRange(range)
    return range
  }

  function emitChange() {
    const editor = editorRef.current
    if (!editor) return
    const next = serializeTelegramEditor(editor)
    if (next.length <= 3500) onChange(next)
    else editor.innerHTML = safeTelegramEditorHtml(value)
    saveSelection()
  }

  function applyFormat(format) {
    const editor = editorRef.current
    const range = activeRange()
    if (!editor || !range) return
    const element = document.createElement(format.tag)
    if (range.collapsed) element.textContent = format.sample
    else element.appendChild(range.extractContents())
    range.insertNode(element)
    const selection = window.getSelection()
    range.selectNodeContents(element)
    selection.removeAllRanges()
    selection.addRange(range)
    editor.focus()
    emitChange()
  }

  function insertDynamic(key) {
    if (!key) return
    const editor = editorRef.current
    const range = activeRange()
    if (!editor || !range) return
    const token = `{${key}}`
    range.deleteContents()
    const text = document.createTextNode(token)
    range.insertNode(text)
    range.setStartAfter(text)
    range.collapse(true)
    const selection = window.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)
    editor.focus()
    emitChange()
  }

  function pastePlainText(event) {
    event.preventDefault()
    const editor = editorRef.current
    const range = activeRange()
    if (!editor || !range) return
    const text = document.createTextNode(event.clipboardData.getData('text/plain'))
    range.deleteContents()
    range.insertNode(text)
    range.setStartAfter(text)
    range.collapse(true)
    const selection = window.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)
    editor.focus()
    emitChange()
  }

  return (
    <div className="col gap-8">
      <div className="row gap-6" style={{ flexWrap: 'wrap', alignItems: 'center' }}>
        {NOTIFICATION_FORMATS.map(format => (
          <button key={format.tag} type="button" className="btn btn-ghost btn-sm"
            title={format.title}
            style={{ minWidth: format.label.length > 2 ? 58 : 36, fontWeight: format.tag === 'b' ? 800 : undefined,
              fontStyle: format.tag === 'i' ? 'italic' : undefined,
              textDecoration: format.tag === 'u' ? 'underline' : format.tag === 's' ? 'line-through' : undefined }}
            onMouseDown={e => e.preventDefault()}
            onClick={() => applyFormat(format)}>
            {format.label}
          </button>
        ))}
      </div>

      <div ref={editorRef} className="input" contentEditable suppressContentEditableWarning
        role="textbox" aria-multiline="true" dir={direction === 'auto' ? 'auto' : direction}
        onInput={emitChange} onPaste={pastePlainText}
        onMouseUp={saveSelection} onKeyUp={saveSelection} onBlur={saveSelection}
        style={{ minHeight: 132, height: 'auto', overflowY: 'auto', whiteSpace: 'pre-wrap',
          lineHeight: 1.55, textAlign: direction === 'rtl' ? 'right' : direction === 'ltr' ? 'left' : 'start' }} />

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(120px, .55fr)', gap: 8 }}>
        <select className="input" value="" onChange={e => insertDynamic(e.target.value)}>
          <option value="">Insert dynamic value…</option>
          {placeholders.map(key => <option key={key} value={key}>
            {`{${key}}${placeholderHelp[key] ? ` — ${placeholderHelp[key]}` : ''}`}
          </option>)}
        </select>
        <select className="input" value={direction} onChange={e => onDirectionChange(e.target.value)}>
          <option value="auto">Direction: Auto</option>
          <option value="ltr">Direction: LTR</option>
          <option value="rtl">Direction: RTL</option>
        </select>
      </div>
      <div style={{ fontSize: 11, color: 'var(--tx-3)', lineHeight: 1.45 }}>
        The editor shows Telegram formatting directly. Select text before choosing a format; dynamic values are inserted at the cursor.
      </div>
    </div>
  )
}

function NotificationsTab({ showToast }) {
  const [rules, setRules] = useState(null)
  const [events, setEvents] = useState([])
  const [form, setForm] = useState({ ...EMPTY_NOTIFICATION_RULE })
  const [editingId, setEditingId] = useState(null)
  const [busy, setBusy] = useState({})
  const [aiOptions, setAiOptions] = useState({ tone: 'fun', length: 'short', instructions: '' })

  const load = useCallback(() => api.admin.notificationRules()
    .then(d => { setRules(d.rules || []); setEvents(d.events || []) })
    .catch(e => { setRules([]); showToast(e.message, 'error') }), [showToast])

  useEffect(() => { load() }, [load])

  function setB(key, value) { setBusy(p => ({ ...p, [key]: value })) }

  function resetForm() {
    setEditingId(null)
    setForm({ ...EMPTY_NOTIFICATION_RULE })
  }

  function editRule(rule) {
    setEditingId(rule.id)
    setForm({
      name: rule.name,
      trigger_type: rule.trigger_type || 'condition',
      event_key: rule.event_key || 'new_round',
      condition_field: rule.condition_field,
      operator: rule.operator,
      threshold: String(rule.threshold),
      message: rule.message,
      text_direction: rule.text_direction || 'auto',
      language: rule.language || 'en',
      enabled: !!rule.enabled,
    })
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function save() {
    const threshold = Number(form.threshold)
    if (!form.name.trim()) { showToast('Enter a rule name', 'error'); return }
    if (form.trigger_type === 'condition' && (!Number.isFinite(threshold) || threshold < 0)) {
      showToast('Enter a valid credit amount', 'error'); return
    }
    if (!form.message.trim()) { showToast('Enter notification text', 'error'); return }
    setB('save', true)
    try {
      const payload = {
        ...form,
        name: form.name.trim(),
        message: form.message.trim(),
        threshold: form.trigger_type === 'condition' ? threshold : 0,
      }
      const result = editingId
        ? await api.admin.updateNotificationRule(editingId, payload)
        : await api.admin.createNotificationRule(payload)
      const sent = result.evaluation?.sent || 0
      showToast(sent ? `Rule saved · ${sent} notification${sent === 1 ? '' : 's'} sent` : 'Rule saved', 'success')
      resetForm()
      await load()
    } catch (e) { showToast(e.message, 'error') }
    finally { setB('save', false) }
  }

  async function toggle(rule) {
    setB(`toggle-${rule.id}`, true)
    try {
      const result = await api.admin.updateNotificationRule(rule.id, { enabled: !rule.enabled })
      const sent = result.evaluation?.sent || 0
      showToast(sent ? `Enabled · ${sent} notification${sent === 1 ? '' : 's'} sent` : (!rule.enabled ? 'Rule enabled' : 'Rule paused'), 'success')
      await load()
    } catch (e) { showToast(e.message, 'error') }
    finally { setB(`toggle-${rule.id}`, false) }
  }

  async function test(rule) {
    setB(`test-${rule.id}`, true)
    try {
      await api.admin.testNotificationRule(rule.id)
      showToast('Test sent to your Telegram', 'success')
    } catch (e) { showToast(e.message, 'error') }
    finally { setB(`test-${rule.id}`, false) }
  }

  async function remove(rule) {
    if (!window.confirm(`Delete “${rule.name}”? Delivery history for this rule will also be removed.`)) return
    setB(`delete-${rule.id}`, true)
    try {
      await api.admin.deleteNotificationRule(rule.id)
      if (editingId === rule.id) resetForm()
      showToast('Rule deleted', 'success')
      await load()
    } catch (e) { showToast(e.message, 'error') }
    finally { setB(`delete-${rule.id}`, false) }
  }

  function selectLanguage(language) {
    setForm(p => ({
      ...p,
      language,
      text_direction: language === 'fa' ? 'rtl' : 'ltr',
    }))
  }

  async function generateWithAI() {
    setB('ai', true)
    try {
      const result = await api.admin.generateNotificationRule({
        trigger_type: form.trigger_type,
        event_key: form.event_key,
        condition_field: form.condition_field,
        operator: form.operator,
        threshold: Number(form.threshold),
        language: form.language || 'en',
        tone: aiOptions.tone,
        length: aiOptions.length,
        instructions: aiOptions.instructions,
        text_direction: form.text_direction || 'auto',
      })
      setForm(p => ({
        ...p,
        message: result.message,
        language: result.language || p.language,
        text_direction: result.text_direction || p.text_direction,
      }))
      showToast('AI notification created — review it before saving', 'success')
    } catch (e) { showToast(e.message, 'error') }
    finally { setB('ai', false) }
  }

  const selectedEvent = events.find(event => event.value === form.event_key)
  const placeholders = form.trigger_type === 'event'
    ? (selectedEvent?.placeholders || ['name', 'group'])
    : ['name', 'credit', 'threshold', 'group']

  function selectTrigger(triggerType) {
    if (triggerType === 'event') {
      const model = selectedEvent || events[0]
      setForm(p => ({
        ...p,
        trigger_type: 'event',
        event_key: model?.value || 'new_round',
        name: model?.label || 'Event notification',
        message: model?.default_message || p.message,
      }))
    } else {
      setForm({ ...EMPTY_NOTIFICATION_RULE })
    }
  }

  function selectEvent(eventKey) {
    const model = events.find(event => event.value === eventKey)
    setForm(p => ({
      ...p,
      event_key: eventKey,
      name: model?.label || p.name,
      message: model?.default_message || p.message,
    }))
  }

  return (
    <div style={{ padding: '12px 16px 24px' }}>
      <div className="card col gap-10" style={{ marginBottom: 14 }}>
        <div className="row between" style={{ alignItems: 'center' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{editingId ? 'Edit automation' : 'Create automation'}</div>
            <div style={{ marginTop: 3, fontSize: 12, color: 'var(--tx-3)' }}>Build a group-specific WHEN / THEN rule</div>
          </div>
          {editingId && <button type="button" className="btn btn-ghost btn-sm" onClick={resetForm}>Cancel</button>}
        </div>

        <FieldLabel label="Rule name">
          <input className="input" maxLength={80} value={form.name}
            onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
        </FieldLabel>

        <FieldLabel label="Trigger model">
          <select className="input" value={form.trigger_type}
            onChange={e => selectTrigger(e.target.value)}>
            <option value="condition">Member condition</option>
            <option value="event">System event</option>
          </select>
        </FieldLabel>

        <div style={{ borderRadius: 12, padding: 12, background: 'rgba(46,166,255,.08)', border: '.5px solid rgba(46,166,255,.22)' }}>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.6px', color: 'var(--tg)', marginBottom: 8 }}>WHEN</div>
          {form.trigger_type === 'condition' ? <>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <select className="input" value={form.condition_field} disabled>
                <option value="credit">Member credit</option>
              </select>
              <select className="input" value={form.operator}
                onChange={e => setForm(p => ({ ...p, operator: e.target.value }))}>
                {Object.entries(NOTIFICATION_OPERATOR_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
            <div style={{ position: 'relative', marginTop: 8 }}>
              <span className="mono" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--tx-3)' }}>$</span>
              <input className="input mono" type="number" min="0" step="0.01" value={form.threshold}
                onChange={e => setForm(p => ({ ...p, threshold: e.target.value }))}
                style={{ paddingLeft: 25 }} />
            </div>
          </> : <>
            <select className="input" value={form.event_key} onChange={e => selectEvent(e.target.value)}>
              {events.map(event => <option key={event.value} value={event.value}>{event.label}</option>)}
            </select>
            {selectedEvent && <div style={{ marginTop: 8, fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
              {selectedEvent.description}<br /><b>Recipients:</b> {selectedEvent.recipient}
            </div>}
          </>}
        </div>

        <div style={{ borderRadius: 12, padding: 12, background: 'rgba(78,208,122,.08)', border: '.5px solid rgba(78,208,122,.22)' }}>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: '.6px', color: 'var(--money)', marginBottom: 8 }}>THEN · SEND TELEGRAM MESSAGE</div>
          <div style={{ borderRadius: 10, padding: 10, marginBottom: 10, background: 'var(--surface-2)', border: '.5px solid var(--hairline)' }}>
            <div className="row between" style={{ marginBottom: 8, alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 750 }}>✨ AI notification creator</div>
                <div style={{ fontSize: 11, color: 'var(--tx-3)', marginTop: 2 }}>Uses the selected WHEN model and its dynamic items</div>
              </div>
              <button type="button" className="btn btn-primary btn-sm" disabled={busy.ai} onClick={generateWithAI}>
                {busy.ai ? 'Creating…' : 'Create with AI'}
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 6 }}>
              <select className="input" value={form.language || 'en'} onChange={e => selectLanguage(e.target.value)}>
                {NOTIFICATION_LANGUAGES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select className="input" value={aiOptions.tone}
                onChange={e => setAiOptions(p => ({ ...p, tone: e.target.value }))}>
                {NOTIFICATION_AI_TONES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
              <select className="input" value={aiOptions.length}
                onChange={e => setAiOptions(p => ({ ...p, length: e.target.value }))}>
                {NOTIFICATION_AI_LENGTHS.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
              </select>
            </div>
            <textarea className="input" rows={2} maxLength={600}
              value={aiOptions.instructions}
              onChange={e => setAiOptions(p => ({ ...p, instructions: e.target.value }))}
              placeholder="Extra instructions, e.g. don’t mention the group name or jackpot"
              style={{ marginTop: 7, resize: 'vertical', lineHeight: 1.45 }} />
          </div>
          <NotificationMessageEditor
            value={form.message}
            onChange={message => setForm(p => ({ ...p, message }))}
            direction={form.text_direction || 'auto'}
            onDirectionChange={text_direction => setForm(p => ({ ...p, text_direction }))}
            placeholders={placeholders}
            placeholderHelp={selectedEvent?.placeholder_help || {}}
          />
        </div>

        <label className="row between" style={{ cursor: 'pointer', padding: '2px 0' }}>
          <span style={{ fontSize: 14 }}>Enable immediately</span>
          <input type="checkbox" checked={form.enabled}
            onChange={e => setForm(p => ({ ...p, enabled: e.target.checked }))} />
        </label>
        <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: 'var(--tx-3)' }}>
          {form.trigger_type === 'condition'
            ? 'A member is notified once when the condition becomes true. The rule resets after their credit no longer matches.'
            : 'This message replaces the built-in message when the selected event occurs. Existing member notification preferences still apply.'}
        </p>
        <button className="btn btn-primary btn-block" disabled={busy.save} onClick={save}>
          {busy.save ? 'Saving…' : editingId ? 'Save changes' : 'Create rule'}
        </button>
      </div>

      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.5px', margin: '0 2px 8px' }}>
        Group rules
      </div>
      {rules === null ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 30 }}><div className="spinner" /></div>
      ) : rules.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', color: 'var(--tx-2)', fontSize: 14 }}>No notification rules yet.</div>
      ) : rules.map(rule => (
        <div key={rule.id} className="card col gap-8" style={{ marginBottom: 10, opacity: rule.enabled ? 1 : .68 }}>
          <div className="row between" style={{ alignItems: 'center' }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>{rule.name}</div>
            <span className={rule.enabled ? 'chip chip-gold' : 'chip'}>{rule.enabled ? 'ACTIVE' : 'PAUSED'}</span>
          </div>
          <div style={{ fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.5 }}>
            <b>WHEN</b>{' '}
            {(rule.trigger_type || 'condition') === 'event'
              ? (events.find(event => event.value === rule.event_key)?.label || rule.event_key)
              : <>member credit {NOTIFICATION_OPERATOR_LABELS[rule.operator]} <span className="mono">{fmtCAD(rule.threshold)}</span></>}
          </div>
          <div dir={(rule.text_direction || 'auto') === 'auto' ? 'auto' : rule.text_direction}
            style={{ fontSize: 13, color: 'var(--tx-2)', lineHeight: 1.5, whiteSpace: 'pre-wrap',
              textAlign: rule.text_direction === 'rtl' ? 'right' : rule.text_direction === 'ltr' ? 'left' : 'start' }}>
            <b>THEN</b> <FormattedNotificationText value={rule.message} direction={rule.text_direction || 'auto'} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--tx-3)' }}>
            Language: {(rule.language || 'en').toUpperCase()} · Direction: {(rule.text_direction || 'auto').toUpperCase()}
          </div>
          <div style={{ fontSize: 12, color: 'var(--tx-3)' }}>
            Sent {Number(rule.sent_count || 0)} time{Number(rule.sent_count || 0) === 1 ? '' : 's'}
            {rule.last_sent_at ? ` · last ${rule.last_sent_at}` : ''}
          </div>
          <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
            <button className="btn btn-ghost btn-sm" onClick={() => editRule(rule)}>Edit</button>
            <button className="btn btn-ghost btn-sm" disabled={busy[`test-${rule.id}`]} onClick={() => test(rule)}>
              {busy[`test-${rule.id}`] ? 'Sending…' : 'Send test'}
            </button>
            <button className="btn btn-ghost btn-sm" disabled={busy[`toggle-${rule.id}`]} onClick={() => toggle(rule)}>
              {rule.enabled ? 'Pause' : 'Enable'}
            </button>
            <button className="btn btn-ghost btn-sm" style={{ color: 'var(--danger)' }}
              disabled={busy[`delete-${rule.id}`]} onClick={() => remove(rule)}>Delete</button>
          </div>
        </div>
      ))}
    </div>
  )
}

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
  const [groupLocked, setGroupLocked] = useState(false)

  const refreshGroupLock = useCallback(
    () => api.admin.group.get()
      .then(d => setGroupLocked(!!d.group?.locked))
      .catch(e => { if (String(e.message || '').includes('GROUP_LOCKED')) setGroupLocked(true) }),
    [],
  )

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
    if (String(err.message || '').includes('GROUP_LOCKED')) { setGroupLocked(true); return }
    setLoadError(err.message || 'Could not load rounds')
    showToast(err.message || 'Could not load rounds', 'error')
  }), [showToast])
  const loadDeposits = useCallback(() => api.admin.deposits().then(d => {
    setDeposits(d.deposits)
    setImapOk(!!d.imap_configured)
  }).catch(err => {
    setDeposits([])
    if (String(err.message || '').includes('GROUP_LOCKED')) { setGroupLocked(true); return }
    showToast(err.message || 'Could not load deposits', 'error')
  }), [showToast])
  const loadMembers  = useCallback(() => api.admin.members().then(d => setMembers(d.members)).catch(err => {
    setMembers([])
    if (String(err.message || '').includes('GROUP_LOCKED')) { setGroupLocked(true); return }
    showToast(err.message || 'Could not load members', 'error')
  }), [showToast])

  useEffect(() => { refreshGroupLock(); loadRounds(); loadDeposits(); loadMembers() },
    [refreshGroupLock, loadRounds, loadDeposits, loadMembers])

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

  const [depAmt, setDepAmt] = useState({})   // per-deposit edited amount (string)

  async function resolveDeposit(id, action, amount) {
    setB(`d${id}`, true)
    try {
      await api.admin.resolve(id, action, amount)
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

  if (groupLocked) {
    return (
      <LockedAdmin
        showToast={showToast}
        onReactivated={() => { refreshGroupLock(); loadRounds(); loadDeposits(); loadMembers() }}
      />
    )
  }

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
      <div style={{ padding: '10px 16px 0', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {[
          { id: 'round',    label: 'Round'   },
          { id: 'deposits', label: pendingCount ? `Deposits (${pendingCount})` : 'Deposits' },
          { id: 'members',  label: 'Members' },
          { id: 'notifications', label: 'Notifications' },
          { id: 'payments', label: 'Settings' },
        ].map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{
              flex: '1 1 92px', padding: '7px 0', borderRadius: 10, border: 'none', cursor: 'pointer',
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
                {st === 'open' && (
                  <button className="btn btn-block"
                    style={{ background: 'rgba(78,208,122,.1)', color: 'var(--money)',
                             border: '.5px solid rgba(78,208,122,.25)' }}
                    disabled={busy.resync}
                    onClick={() => {
                      if (!window.confirm('Re-apply free tickets from the last draw to this round, shared proportionally by each member’s stake?')) return
                      roundAction('resync',
                        () => api.admin.resyncFreeTickets(round.id),
                        (r) => r.free_value_total > 0
                          ? `Applied $${Number(r.free_value_total).toFixed(2)} free stake across the pool.`
                          : 'No pending free tickets to apply.')
                    }}>
                    {busy.resync ? 'Applying…' : '🎁 Re-sync free tickets'}
                  </button>
                )}
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
              {d.payment_method === 'etransfer' && (
                <div className="row gap-8" style={{ alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Amount to credit</span>
                  <div style={{ position: 'relative', width: 130, marginLeft: 'auto' }}>
                    <span className="mono" style={{ position: 'absolute', left: 10, top: '50%',
                      transform: 'translateY(-50%)', color: 'var(--tx-3)', fontSize: 14 }}>$</span>
                    <input type="number" inputMode="decimal" step="0.01" min="0" className="input mono"
                      value={depAmt[d.id] ?? String(d.amount)}
                      onChange={e => setDepAmt(p => ({ ...p, [d.id]: e.target.value }))}
                      style={{ paddingLeft: 22, textAlign: 'right', height: 40 }} />
                  </div>
                </div>
              )}
              <div className="row gap-8">
                <button className="btn btn-block"
                  style={{ flex: 1, background: 'rgba(78,208,122,.12)', color: 'var(--money)', border: 'none' }}
                  disabled={busy[`d${d.id}`]}
                  onClick={() => {
                    const raw = depAmt[d.id]
                    const amt = raw != null && raw !== '' ? Number(raw) : d.amount
                    if (!(amt > 0)) { showToast('Enter a valid amount', 'error'); return }
                    resolveDeposit(d.id, 'approve', amt)
                  }}>
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
        <PaymentsTab showToast={showToast} onGroupChange={refreshGroupLock} />
      )}

      {tab === 'notifications' && (
        <NotificationsTab showToast={showToast} />
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
