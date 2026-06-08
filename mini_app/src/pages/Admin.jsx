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
              <div style={{ fontSize: 10, color: 'var(--tx-3)', marginBottom: 6, fontWeight: 600,
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
        tickets_target:  Number(target)  || 25,
        price_per_share: Number(price)   || 6,
      })
      showToast(`Round #${res.round_id} opened!`, 'success')
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
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{lt.name}</div>
                      <div style={{
                        fontSize: 10, fontWeight: 500,
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
                            fontSize: 9, fontWeight: 700, letterSpacing: '.4px',
                            textTransform: 'uppercase', color: sel ? 'var(--tg)' : 'var(--money)',
                          }}>
                            Next
                          </span>
                        )}
                        <span style={{
                          fontSize: 13, fontWeight: 600,
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
                <span style={{ fontSize: 11, color: 'var(--tx-3)', lineHeight: 1.45 }}>
                  {isFutureDraw
                    ? 'Not published for this draw yet. You can open the round now and set the jackpot later.'
                    : 'Not published yet. Open the round and set it later, or it will fill in automatically when lotto.ca publishes it.'}
                </span>
              )}
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
      <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
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
      <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--tx-3)', fontStyle: 'italic' }}>
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
      <span style={{ fontSize: 10, color: 'var(--tx-3)', marginTop: -4 }}>
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
        <span style={{ fontSize: 10, color: 'var(--tx-3)', lineHeight: 1.4 }}>
          Auto-fetch becomes available when this draw is the next one on lotto.ca.
        </span>
      )}
    </div>
  )
}

// ── Upload Ticket Sheet (camera + Tesseract OCR, multi-ticket) ───────────
function UploadTicketSheet({ round, onClose, onUploaded, showToast }) {
  const layout = ticketLayout(round?.lottery_type)
  const required = round?.tickets_required ?? 1
  const alreadySaved = (round?.round_tickets || []).filter(t => t?.rows?.length).length
  const [ticketIndex, setTicketIndex] = useState(alreadySaved)
  const [savedCount, setSavedCount] = useState(alreadySaved)
  const [rows, setRows] = useState(() => emptyTicketRows(layout))
  const [busy, setBusy] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [ocrPct, setOcrPct] = useState(0)
  const [preview, setPreview] = useState(null)
  const [previewB64, setPreviewB64] = useState(null)
  const [scanDate, setScanDate] = useState(null)
  const [cameraOpen, setCameraOpen] = useState(false)
  const [showNextPrompt, setShowNextPrompt] = useState(false)
  const galleryRef = useRef()
  const cameraFileRef = useRef()

  const ticketNum = Math.min(ticketIndex + 1, required)
  const allDone = savedCount >= required

  function resetForNextScan() {
    setRows(emptyTicketRows(layout))
    setPreview(null)
    setPreviewB64(null)
    setShowNextPrompt(false)
  }

  function setNum(rowIdx, colIdx, v, spec) {
    const maxLen = spec.max >= 10 ? 2 : 1
    const next = rows.map((row, ri) =>
      ri === rowIdx
        ? row.map((cell, ci) => (ci === colIdx ? v.replace(/\D/g, '').slice(0, maxLen) : cell))
        : [...row],
    )
    setRows(next)
    const val = v.replace(/\D/g, '').slice(0, maxLen)
    if (val.length >= maxLen && colIdx < spec.count - 1) {
      document.getElementById(`tn-${rowIdx}-${colIdx + 1}`)?.focus()
    } else if (val.length >= maxLen && rowIdx < rows.length - 1) {
      document.getElementById(`tn-${rowIdx + 1}-0`)?.focus()
    }
  }

  async function processDataUrl(dataUrl) {
    if (!dataUrl) return
    setPreview(dataUrl)
    setPreviewB64(dataUrl)
    setScanning(true)
    setOcrPct(0)
    try {
      const scanned = await scanTicketImage(dataUrl, round.lottery_type, setOcrPct)
      const merged = scanned.length ? mergeScannedRows(scanned, layout) : emptyTicketRows(layout)
      setRows(merged)
      if (scanned.length) {
        const filled = ticketRowsValid(merged, layout)
        const n = merged.length
        showToast(
          filled
            ? `OCR found ${n} line${n === 1 ? '' : 's'} — review and save`
            : `OCR found ${n} line${n === 1 ? '' : 's'} — fill any missing numbers`,
          filled ? 'success' : 'info',
        )
      } else {
        showToast('OCR could not read numbers — enter them manually', 'info')
      }
      // Image + rows are persisted when trustee taps Save ticket
    } catch (err) {
      showToast('Scan failed: ' + err.message, 'error')
    } finally {
      setScanning(false)
      setOcrPct(0)
    }
  }

  async function processImage(file) {
    if (!file) return
    await processDataUrl(await compressImage(file))
  }

  function handleFilePick(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    processImage(file)
  }

  function openCamera() {
    if (navigator.mediaDevices?.getUserMedia) {
      setCameraOpen(true)
      return
    }
    cameraFileRef.current?.click()
  }

  const scanBtnStyle = {
    flex: 1, gap: 8, background: 'rgba(46,166,255,.12)', color: 'var(--tg)',
    border: '.5px solid rgba(46,166,255,.25)',
  }

  const valid = ticketRowsValid(rows, layout)
  const variableRows = isVariableRowLayout(layout)

  async function saveCurrentTicket() {
    if (!valid || !previewB64) return
    setBusy(true)
    try {
      const nums = ticketRowsToNumbers(rows)
      const res = await api.admin.saveTicket(
        round.id, ticketIndex, nums, previewB64, scanDate || undefined,
      )
      const uploaded = res.tickets_uploaded ?? savedCount + 1
      setSavedCount(uploaded)
      showToast(`Ticket ${ticketNum} of ${required} saved`, 'success')
      if (uploaded >= required) {
        await finalizeUpload()
        return
      }
      setShowNextPrompt(true)
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  async function finalizeUpload() {
    setBusy(true)
    try {
      await api.admin.uploadTicket(round.id)
      showToast(
        savedCount >= required
          ? `All ${required} ticket${required === 1 ? '' : 's'} uploaded!`
          : 'Ticket numbers uploaded!',
        'success',
      )
      onUploaded()
      onClose()
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  function onNextTicket() {
    setTicketIndex(i => i + 1)
    resetForNextScan()
  }

  const dateMismatch = scanDate && round?.draw_date && scanDate !== round.draw_date

  if (showNextPrompt) {
    const remaining = required - savedCount
    return (
      <div className="sheet-overlay" onClick={onClose}>
        <div className="sheet" onClick={e => e.stopPropagation()}>
          <div className="handle" />
          <div className="sheet-head">
            <span className="sheet-title">Ticket {ticketNum} saved</span>
            <button className="sheet-close" onClick={onClose}>✕</button>
          </div>
          <div className="body">
            <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.5, marginBottom: 16 }}>
              {savedCount} of {required} ticket{required === 1 ? '' : 's'} uploaded.
              {remaining > 0
                ? ` Scan ${remaining} more physical ticket${remaining === 1 ? '' : 's'} purchased for this round.`
                : ''}
            </p>
            <div className="col" style={{ gap: 8 }}>
              {remaining > 0 && (
                <button type="button" className="btn btn-primary btn-block" onClick={onNextTicket}>
                  <CameraIcon width={16} height={16} />
                  Next ticket ({savedCount + 1} of {required})
                </button>
              )}
              <button type="button" className="btn btn-block"
                style={{ background: 'var(--surface-2)' }}
                disabled={busy || savedCount < required}
                onClick={finalizeUpload}>
                <CheckIcon width={16} height={16} />
                {busy ? 'Finishing…' : savedCount < required
                  ? `Need ${remaining} more ticket${remaining === 1 ? '' : 's'}`
                  : 'Finished — notify group'}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">
            Ticket {ticketNum} of {required} · Round #{round?.id}
          </span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">

          <div style={{
            fontSize: 12, borderRadius: 8, padding: '8px 12px', marginBottom: 12,
            background: allDone ? 'rgba(78,208,122,.1)' : 'rgba(46,166,255,.1)',
            color: allDone ? 'var(--money)' : 'var(--tg)',
            border: `.5px solid ${allDone ? 'rgba(78,208,122,.3)' : 'rgba(46,166,255,.25)'}`,
          }}>
            {savedCount} of {required} ticket{required === 1 ? '' : 's'} saved
            {required > 1 && ' · one scan per physical ticket bought in the pool'}
          </div>

          <input ref={galleryRef} type="file" accept="image/*"
            style={{ display: 'none' }} onChange={handleFilePick} />
          <input ref={cameraFileRef} type="file" accept="image/*" capture="environment"
            style={{ display: 'none' }} onChange={handleFilePick} />

          {cameraOpen && (
            <CameraCapture
              onClose={() => setCameraOpen(false)}
              onCapture={dataUrl => {
                setCameraOpen(false)
                processDataUrl(dataUrl)
              }}
              onError={msg => showToast(msg, 'error')}
            />
          )}

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
                  <span style={{ fontSize: 13, color: '#fff', fontWeight: 600 }}>
                    Reading ticket…{ocrPct ? ` ${ocrPct}%` : ''}
                  </span>
                </div>
              )}
              {!scanning && (
                <div style={{
                  position: 'absolute', bottom: 8, left: 8, right: 8,
                  display: 'flex', gap: 8,
                }}>
                  <button type="button" className="btn" disabled={scanning}
                    onClick={openCamera}
                    style={{ flex: 1, padding: '8px 10px', fontSize: 12, fontWeight: 700,
                      background: 'rgba(46,166,255,.95)', color: '#fff', border: 'none', gap: 6 }}>
                    <CameraIcon width={14} height={14} /> Retake
                  </button>
                  <button type="button" className="btn" disabled={scanning}
                    onClick={() => galleryRef.current?.click()}
                    style={{ flex: 1, padding: '8px 10px', fontSize: 12, fontWeight: 700,
                      background: 'rgba(13,20,27,.85)', color: '#fff', border: 'none', gap: 6 }}>
                    <UploadIcon width={14} height={14} /> Replace
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
              <button type="button" className="btn btn-block" disabled={scanning}
                onClick={openCamera} style={scanBtnStyle}>
                <CameraIcon width={18} height={18} />
                Take photo
              </button>
              <button type="button" className="btn btn-block" disabled={scanning}
                onClick={() => galleryRef.current?.click()} style={scanBtnStyle}>
                <UploadIcon width={18} height={18} />
                Upload photo
              </button>
            </div>
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
            Numbers on this ticket
          </div>
          <div className="col" style={{ gap: 14, marginBottom: 16, maxHeight: 280, overflowY: 'auto' }}>
            {rows.map((_, rowIdx) => {
              const spec = rowSpecForIndex(layout, rowIdx)
              return (
                <div key={`row-${rowIdx}`}>
                  <div className="row between" style={{ marginBottom: 6 }}>
                    <div style={{ fontSize: 10, color: 'var(--tx-3)', fontWeight: 600,
                      textTransform: 'uppercase', letterSpacing: '.3px' }}>
                      {spec.label} ({spec.min}–{spec.max})
                    </div>
                    {variableRows && rows.length > 1 && (
                      <button type="button" onClick={() => setRows(removeTicketRow(layout, rows, rowIdx))}
                        style={{ background: 'none', border: 'none', color: 'var(--danger)',
                          fontSize: 11, fontWeight: 600, cursor: 'pointer', padding: 0 }}>
                        Remove
                      </button>
                    )}
                  </div>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${spec.count}, 1fr)`,
                    gap: 6,
                  }}>
                    {(rows[rowIdx] || []).map((v, colIdx) => (
                      <input
                        key={colIdx}
                        id={`tn-${rowIdx}-${colIdx}`}
                        value={v}
                        maxLength={spec.max >= 10 ? 2 : 1}
                        inputMode="numeric"
                        onChange={e => setNum(rowIdx, colIdx, e.target.value, spec)}
                        className="input num-input"
                        style={{ padding: 0, textAlign: 'center', fontSize: 16, fontWeight: 700, height: 44 }}
                      />
                    ))}
                  </div>
                </div>
              )
            })}
            {variableRows && rows.length < (layout.maxRows ?? 10) && (
              <button type="button" className="btn btn-block"
                style={{ background: 'var(--surface-2)', fontSize: 13 }}
                onClick={() => setRows(addTicketRow(layout, rows))}>
                <PlusIcon width={14} height={14} /> Add line
              </button>
            )}
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <SummaryRow k="Shares bought"  v={required} mono />
            <SummaryRow k="Pool total"     v={fmtCAD(round?.pool)} mono />
            <SummaryRow k="Draw date"      v={round?.draw_date ? fmtDate(round.draw_date) : '—'} />
          </div>

          <button className="btn btn-primary btn-block"
            disabled={!valid || busy || scanning || !previewB64}
            onClick={saveCurrentTicket}>
            <UploadIcon width={16} height={16} />
            {busy ? 'Saving…' : scanning ? 'Scanning…' : `Save ticket ${ticketNum}`}
          </button>
          {savedCount > 0 && (
            <button type="button" className="btn btn-block" style={{ marginTop: 8, background: 'var(--surface-2)' }}
              disabled={busy || savedCount < required}
              onClick={finalizeUpload}>
              {savedCount < required
                ? `Finished (${savedCount}/${required} — need ${required - savedCount} more)`
                : 'Finished — notify group'}
            </button>
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
          <span className="sheet-title">Enter results · Round #{round?.id}</span>
          <button className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body">
          <p style={{ fontSize: 13, color: 'var(--tx-2)', marginBottom: 16, lineHeight: 1.5 }}>
            {hasTickets
              ? 'Tap numbers from the ticket to set the 7 winning numbers and bonus. Prize allocation is computed automatically.'
              : 'Enter the 7 winning numbers and bonus. Prize allocation is computed automatically and distributed to participants proportionally.'}
          </p>

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
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
                <span style={{ color: 'var(--tx-3)', fontSize: 18, fontWeight: 700 }}>+</span>
                <button type="button" onClick={() => (bonus ? clearBonus() : setPickBonus(true))}
                  style={{ border: 'none', background: 'none', padding: 0, cursor: 'pointer' }}>
                  <span className={`ball md ${bonus ? 'bonus' : 'def'}`}
                    style={pickBonus ? { outline: '2px solid var(--gold)', outlineOffset: 2 } : undefined}>
                    {bonus || '—'}
                  </span>
                </button>
              </div>
              {pickBonus && (
                <p style={{ fontSize: 12, color: 'var(--gold)', marginBottom: 10 }}>
                  Tap a ticket number for the bonus
                </p>
              )}

              <div style={{ fontSize: 11, color: 'var(--tx-3)', fontWeight: 600, letterSpacing: '.3px',
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
            </>
          )}

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8, marginTop: hasTickets ? 16 : 0 }}>
            Cash prize (CAD)
          </div>
          <input value={totalPrize} onChange={e => setTotalPrize(e.target.value)}
            placeholder="0.00" type="number" inputMode="decimal" min="0"
            className="input mono" style={{ marginBottom: 16 }}
          />

          <div style={{ fontSize: 11, color: 'var(--tx-2)', fontWeight: 600, letterSpacing: '.3px',
                        textTransform: 'uppercase', marginBottom: 8 }}>
            Free tickets won
          </div>
          <input value={freeTickets} onChange={e => setFreeTickets(e.target.value.replace(/\D/g, ''))}
            placeholder="0" type="number" inputMode="numeric" min="0"
            className="input mono" style={{ marginBottom: 8 }}
          />
          <p style={{ margin: '0 0 16px', fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
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
                fontFamily: 'inherit', fontSize: 14, fontWeight: 600,
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
            <p style={{ margin: 0, fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
              Members pick $25, $50, $100, or $250 for card. E-transfer options are the same amounts at or above your minimum.
            </p>
          </>
        )}

        {(pm === 'card' || pm === 'both') && !group.stripe_configured && (
          <p style={{ margin: 0, fontSize: 12, color: 'var(--warn)' }}>
            Stripe is not configured on the server — card payments will not work until it is.
          </p>
        )}
      </div>

      <div className="card col" style={{ gap: 14, marginBottom: 12 }}>
        <FieldLabel label="Free ticket prizes">
          <p style={{ margin: '0 0 4px', fontSize: 12, color: 'var(--tx-3)', lineHeight: 1.5 }}>
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
                fontFamily: 'inherit', fontSize: 14, fontWeight: 600,
              }}>
                <div>{o.label}</div>
                <div style={{ fontSize: 12, fontWeight: 400, color: 'var(--tx-3)', marginTop: 4, lineHeight: 1.45 }}>
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
              <span style={{ fontSize: 15, fontWeight: 600 }}>Your group dashboard</span>
              <span style={{ fontSize: 11, color: 'var(--tx-2)' }}>
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
          { id: 'payments', label: 'Settings' },
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
          {rounds === undefined ? (
            <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 40 }}>
              <div className="spinner" />
            </div>
          ) : (
            <>
          {loadError && (
            <div className="card" style={{ padding: 12, marginBottom: 12, borderColor: 'var(--danger)' }}>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--danger)' }}>{loadError}</p>
            </div>
          )}
          {rounds.length === 0 && !loadError && (
            <div className="card" style={{ padding: 16, marginBottom: 12, textAlign: 'center' }}>
              <p style={{ margin: '0 0 8px', fontWeight: 600 }}>No rounds yet</p>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--tx-2)' }}>
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
                    fontFamily: 'inherit', fontSize: 12, fontWeight: 600,
                    color: sel ? 'var(--tg)' : 'var(--tx-1)',
                  }}>
                    <LotteryLogo type={r.lottery_type} height={18} style={{ width: 28 }} />
                    #{r.id}
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
                  <span style={{ fontSize: 15, fontWeight: 700 }}>Round #{round.id}</span>
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
                    <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{k}</span>
                    <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{v}</span>
                  </div>
                ))}
              </div>

              {(round.jackpot_pending && (st === 'open' || st === 'closed')) ? (
                <div style={{ marginBottom: 12 }}>
                  <span style={{
                    display: 'block', fontSize: 10, color: 'var(--tx-3)',
                    textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8,
                  }}>
                    Jackpot
                  </span>
                  <RoundJackpotEditor round={round} onUpdated={loadRounds} showToast={showToast} />
                </div>
              ) : (
                <div className="col gap-4" style={{ marginBottom: 12 }}>
                  <span style={{ fontSize: 10, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px' }}>Jackpot</span>
                  <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
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
                  <TicketNumbersView
                    ticketNumbers={round.ticket_numbers}
                    lotteryType={round.lottery_type}
                  />
                </>
              )}

              {(round.tickets_required > 1 || round.tickets_uploaded > 0) && (
                <>
                  <div style={{ height: '.5px', background: 'var(--hairline)', margin: '8px 0 12px' }} />
                  <div style={{ fontSize: 11, color: 'var(--tx-3)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 8 }}>
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
                  onClick={() => roundAction('close', () => api.admin.closeRound(round.id), r => `Round #${r.round_id} closed.`)}>
                  {busy.close ? 'Closing…' : `Close round #${round.id}`}
                </button>
                <button className="btn btn-block"
                  style={{ background: canUpload ? 'rgba(46,166,255,.12)' : 'var(--surface-2)',
                           color: canUpload ? 'var(--tg)' : undefined, opacity: canUpload ? 1 : .4 }}
                  disabled={!canUpload}
                  onClick={() => setShowUp(true)}>
                  <CameraIcon width={16} height={16} />
                  Scan tickets
                  {round.tickets_required > 1 && (
                    <span style={{ fontSize: 11, opacity: 0.85 }}>
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
                    <span style={{ fontWeight: 500, fontSize: 14 }}>
                      {m.full_name}
                      {m.is_group_trustee && (
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
