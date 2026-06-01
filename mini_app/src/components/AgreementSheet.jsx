import { useState, useEffect } from 'react'
import { authFetch } from '../api.js'

async function downloadAgreementPdf(kind, roundId) {
  const path = kind === 'master'
    ? '/api/agreement/master/download'
    : `/api/agreement/round/${roundId}/download`
  const res = await authFetch(path)
  if (!res.ok) {
    const text = await res.text()
    let msg = text
    try { msg = JSON.parse(text).detail ?? text } catch {}
    throw new Error(msg)
  }
  const blob = await res.blob()
  const name = kind === 'master'
    ? 'lotto-chee-group-prize-agreement.pdf'
    : `lotto-chee-round-${roundId}-agreement.pdf`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}

export function AgreementSheet({ kind, roundId, title, onClose }) {
  const [doc, setDoc] = useState(null)
  const [err, setErr] = useState(null)
  const [downloading, setDownloading] = useState(false)

  const isRound = kind === 'round'

  useEffect(() => {
    const load = isRound
      ? api.agreement.round(roundId)
      : api.agreement.master()
    load.then(setDoc).catch(e => setErr(e.message))
  }, [kind, roundId, isRound])

  async function onDownload() {
    if (!doc) return
    setDownloading(true)
    try {
      await downloadAgreementPdf(kind, roundId)
    } catch (e) {
      setErr(e.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">{title || doc?.title || 'Agreement'}</span>
          <button type="button" className="sheet-close" onClick={onClose}>✕</button>
        </div>
        <div className="body" style={{ paddingBottom: 8 }}>
          {err ? (
            <p style={{ fontSize: 13, color: 'var(--danger)' }}>{err}</p>
          ) : !doc ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
              <div className="spinner" />
            </div>
          ) : (
            <>
              <pre style={{
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                fontSize: 12, lineHeight: 1.55, color: 'var(--tx-2)',
                background: 'var(--bg-3)', borderRadius: 12, padding: 14,
                maxHeight: '52dvh', overflow: 'auto', margin: 0,
              }}>{doc.body}</pre>
              <button type="button" className="btn btn-primary btn-block"
                style={{ marginTop: 14 }}
                disabled={downloading}
                onClick={onDownload}>
                {downloading ? 'Preparing PDF…' : 'Download PDF'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export function AgreementLink({ kind, roundId, label, disabled, disabledHint }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => !disabled && setOpen(true)}
        disabled={disabled}
        style={{
          background: 'none', border: 'none', cursor: disabled ? 'default' : 'pointer',
          padding: 0, display: 'flex', alignItems: 'center', gap: 6,
          color: disabled ? 'var(--tx-3)' : 'var(--tg)',
          fontSize: 12, fontWeight: 600, opacity: disabled ? 0.65 : 1,
        }}>
        📄 {label}
      </button>
      {disabled && disabledHint && (
        <span style={{ fontSize: 11, color: 'var(--tx-3)', display: 'block', marginTop: 4 }}>
          {disabledHint}
        </span>
      )}
      {open && (
        <AgreementSheet
          kind={kind}
          roundId={roundId}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
