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

export default function CameraCapture({ onCapture, onClose, onError }) {
  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)

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
        try {
          return await navigator.mediaDevices.getUserMedia(constraints)
        } catch (e) {
          lastErr = e
        }
      }
      throw lastErr
    }

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        onError?.('Camera not supported here — use Upload photo and pick Camera from the menu')
        onClose?.()
        return
      }
      try {
        const stream = await getStream()
        if (cancelled) {
          stream.getTracks().forEach(t => t.stop())
          return
        }
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
          msg = 'Camera permission denied — allow camera access for Telegram in system settings'
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
    if (!video || busy) return
    setBusy(true)
    try {
      const dataUrl = captureVideoFrame(video)
      streamRef.current?.getTracks().forEach(t => t.stop())
      onCapture(dataUrl)
    } catch (err) {
      onError?.(err.message || 'Could not capture photo')
      setBusy(false)
    }
  }

  return (
    <div
      className="sheet-overlay"
      style={{ zIndex: 1200 }}
      onClick={onClose}
    >
      <div
        className="sheet"
        style={{ maxHeight: 'var(--sheet-max-h)' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">Take ticket photo</span>
          <button type="button" className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body" style={{ paddingTop: 0 }}>
          <div style={{
            position: 'relative', borderRadius: 12, overflow: 'hidden',
            background: '#000', aspectRatio: '4/3', marginBottom: 12,
          }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%', height: '100%', objectFit: 'cover',
                opacity: ready ? 1 : 0.3,
              }}
            />
            {!ready && (
              <div style={{
                position: 'absolute', inset: 0, display: 'flex',
                alignItems: 'center', justifyContent: 'center',
              }}>
                <div className="spinner" />
              </div>
            )}
          </div>
          <p style={{ margin: '0 0 12px', fontSize: 12, color: 'var(--tx-2)', lineHeight: 1.5, textAlign: 'center' }}>
            Frame the full ticket so all number rows are visible
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button type="button" className="btn btn-block"
              style={{ background: 'var(--surface-2)' }}
              disabled={busy}
              onClick={onClose}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary btn-block"
              disabled={!ready || busy}
              onClick={snap}>
              {busy ? 'Capturing…' : 'Capture'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
