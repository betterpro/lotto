import { useState, useEffect } from 'react'
import { api } from '../api.js'

function downloadText(filename, text) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function AgreementSheet({ kind, roundId, title, onClose }) {
  const [doc, setDoc] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    const load = kind === 'master'
      ? api.agreement.master()
      : api.agreement.round(roundId)
    load.then(setDoc).catch(e => setErr(e.message))
  }, [kind, roundId])

  const onDownload = () => {
    if (!doc) return
    const name = kind === 'master'
      ? 'lotto-chee-trustee-agreement.txt'
      : `lotto-chee-round-${roundId}-agreement.txt`
    downloadText(name, doc.body)
  }

  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()} style={{ maxHeight: '88dvh' }}>
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
              <a href={doc.bclc_url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 12, color: 'var(--tg)', fontWeight: 600, display: 'block', marginBottom: 12 }}>
                BCLC Group Release Form (PDF) ↗
              </a>
              <pre style={{
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                fontSize: 12, lineHeight: 1.55, color: 'var(--tx-2)',
                background: 'var(--bg-3)', borderRadius: 12, padding: 14,
                maxHeight: '52dvh', overflow: 'auto', margin: 0,
              }}>{doc.body}</pre>
              <button type="button" className="btn btn-primary btn-block"
                style={{ marginTop: 14 }} onClick={onDownload}>
                Download .txt
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
