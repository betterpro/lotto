import { useEffect, useRef, useState } from 'react'

function captureVideoFrame(video, maxPx = 1568, quality = 0.9) {
  let w = video.videoWidth
  let h = video.videoHeight
  if (!w || !h) throw new Error('Camera not ready')
  if (w > maxPx || h > maxPx) {
    if (w > h) { h = Math.round(h * maxPx / w); w = maxPx }
    else { w = Math.round(w * maxPx / h); h = maxPx }
  }
  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  canvas.getContext('2d').drawImage(video, 0, 0, w, h)
  return canvas.toDataURL('image/jpeg', quality)
}

const TIPS = [
  'Lay the ticket flat on a dark surface',
  'Fill the frame — every number row visible',
  'Avoid glare, shadows and blur',
]

/**
 * Full-screen ticket camera.
 * - series=true keeps the camera open after each shot so the trustee can
 *   capture several physical tickets in a row, then tap Done.
 * - onCapture(dataUrl) fires per shot; onClose() when finished/cancelled.
 */
export default function CameraCapture({
  onCapture, onClose, onError,
  series = false, captured = 0, target = 0, thumbs = [],
}) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [ready, setReady] = useState(false)
  const [cooldown, setCooldown] = useState(false)
  const [flash, setFlash] = useState(false)
  const [showTips, setShowTips] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function getStream() {
      const tries = [
        { video: { facingMode: { ideal: 'environment' } }, audio: false },
        { video: { facingMode: 'environment' }, audio: false },
        { video: true, audio: false },
      ]
      let lastErr
      for (const constraints of tries) {
        try { return await navigator.mediaDevices.getUserMedia(constraints) }
        catch (e) { lastErr = e }
      }
      throw lastErr
    }

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        onError?.('Camera not supported here — use Upload photo instead')
        onClose?.()
        return
      }
      try {
        const stream = await getStream()
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return }
        streamRef.current = stream
        const video = videoRef.current
        if (video) {
          video.srcObject = stream
          await video.play()
          setReady(true)
        }
      } catch (err) {
        const name = err?.name || ''
        let msg = 'Could not open camera'
        if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
          msg = 'Camera permission denied — allow camera access in settings'
        } else if (name === 'NotFoundError') {
          msg = 'No camera found on this device'
        }
        onError?.(msg)
        onClose?.()
      }
    }

    start()
    return () => {
      cancelled = true
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
  }, [onClose, onError])

  function snap() {
    const video = videoRef.current
    if (!video || cooldown || !ready) return
    let dataUrl
    try {
      dataUrl = captureVideoFrame(video)
    } catch (err) {
      onError?.(err.message || 'Could not capture photo')
      return
    }
    setFlash(true)
    setTimeout(() => setFlash(false), 150)
    setShowTips(false)
    if (series) {
      setCooldown(true)
      setTimeout(() => setCooldown(false), 450)
      onCapture(dataUrl)
    } else {
      streamRef.current?.getTracks().forEach(t => t.stop())
      onCapture(dataUrl)
    }
  }

  const recentThumbs = thumbs.slice(-4)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 2000, background: '#000',
      display: 'flex', flexDirection: 'column',
    }}>
      {/* Live camera */}
      <video
        ref={videoRef}
        autoPlay playsInline muted
        style={{
          position: 'absolute', inset: 0, width: '100%', height: '100%',
          objectFit: 'cover', opacity: ready ? 1 : 0.25,
        }}
      />

      {/* Shutter flash */}
      {flash && <div style={{ position: 'absolute', inset: 0, background: '#fff', opacity: 0.5 }} />}

      {/* Framing guide */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
        <div style={{
          position: 'absolute', top: '16%', bottom: '24%', left: '7%', right: '7%',
          borderRadius: 16, boxShadow: '0 0 0 100vmax rgba(0,0,0,.35)',
        }}>
          {[
            { top: -2, left: -2, borderWidth: '3px 0 0 3px', borderRadius: '16px 0 0 0' },
            { top: -2, right: -2, borderWidth: '3px 3px 0 0', borderRadius: '0 16px 0 0' },
            { bottom: -2, left: -2, borderWidth: '0 0 3px 3px', borderRadius: '0 0 0 16px' },
            { bottom: -2, right: -2, borderWidth: '0 3px 3px 0', borderRadius: '0 0 16px 0' },
          ].map((pos, i) => (
            <span key={i} style={{
              position: 'absolute', width: 28, height: 28,
              borderStyle: 'solid', borderColor: 'rgba(255,255,255,.9)', ...pos,
            }} />
          ))}
        </div>
      </div>

      {/* Top bar */}
      <div style={{
        position: 'relative', zIndex: 2, display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', padding: '14px 16px',
        background: 'linear-gradient(rgba(0,0,0,.55), rgba(0,0,0,0))',
        paddingTop: 'max(14px, env(safe-area-inset-top))',
      }}>
        <button type="button" onClick={onClose}
          style={{ background: 'rgba(0,0,0,.4)', border: 'none', color: '#fff',
            borderRadius: 20, padding: '8px 14px', fontSize: 15, fontWeight: 600, cursor: 'pointer' }}>
          Close
        </button>
        <span style={{ color: '#fff', fontSize: 15, fontWeight: 700, textShadow: '0 1px 3px rgba(0,0,0,.6)' }}>
          {series && target
            ? `Ticket ${Math.min(captured + 1, target)} of ${target}`
            : 'Take ticket photo'}
        </span>
        <div style={{ width: 64 }} />
      </div>

      {/* Guidelines */}
      {showTips && (
        <div style={{
          position: 'relative', zIndex: 2, margin: '8px 16px 0', alignSelf: 'center',
          maxWidth: 360, background: 'rgba(0,0,0,.55)', borderRadius: 14, padding: '12px 14px',
          backdropFilter: 'blur(2px)',
        }}>
          <div style={{ color: '#fff', fontSize: 14, fontWeight: 700, marginBottom: 6 }}>
            How to get a clean scan
          </div>
          {TIPS.map(t => (
            <div key={t} style={{ display: 'flex', gap: 8, alignItems: 'flex-start', marginTop: 4 }}>
              <span style={{ color: 'var(--money, #4ed07a)', fontSize: 14, lineHeight: '18px' }}>✓</span>
              <span style={{ color: 'rgba(255,255,255,.9)', fontSize: 13, lineHeight: '18px' }}>{t}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Bottom controls */}
      <div style={{
        position: 'relative', zIndex: 2,
        padding: '16px 20px', paddingBottom: 'max(20px, env(safe-area-inset-bottom))',
        background: 'linear-gradient(rgba(0,0,0,0), rgba(0,0,0,.6))',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12,
      }}>
        {/* Left: captured filmstrip / count */}
        <div style={{ width: 96, display: 'flex', alignItems: 'center', gap: 4 }}>
          {series && captured > 0 ? (
            <>
              <div style={{ display: 'flex' }}>
                {recentThumbs.map((src, i) => (
                  <img key={i} src={src} alt="" style={{
                    width: 34, height: 34, borderRadius: 6, objectFit: 'cover',
                    border: '1.5px solid #fff', marginLeft: i ? -12 : 0,
                  }} />
                ))}
              </div>
              <span style={{ color: '#fff', fontSize: 14, fontWeight: 700 }}>{captured}</span>
            </>
          ) : null}
        </div>

        {/* Center: shutter */}
        <button type="button" onClick={snap} disabled={!ready || cooldown} aria-label="Capture"
          style={{
            width: 72, height: 72, borderRadius: '50%', border: '4px solid rgba(255,255,255,.85)',
            background: ready && !cooldown ? '#fff' : 'rgba(255,255,255,.4)',
            cursor: ready && !cooldown ? 'pointer' : 'default', flexShrink: 0,
            boxShadow: '0 2px 12px rgba(0,0,0,.4)',
          }}>
          {!ready && <span className="spinner" style={{ margin: '0 auto' }} />}
        </button>

        {/* Right: done (series) */}
        <div style={{ width: 96, display: 'flex', justifyContent: 'flex-end' }}>
          {series ? (
            <button type="button" onClick={onClose} disabled={captured === 0}
              style={{
                background: captured > 0 ? 'var(--tg, #2ea6ff)' : 'rgba(255,255,255,.18)',
                color: '#fff', border: 'none', borderRadius: 20, padding: '10px 16px',
                fontSize: 15, fontWeight: 700, cursor: captured > 0 ? 'pointer' : 'default',
              }}>
              Done{captured > 0 ? ` (${captured})` : ''}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
}
