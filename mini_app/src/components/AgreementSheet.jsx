import { useState, useEffect } from 'react'
import { api } from '../api.js'

function isSectionHeader(line) {
  const t = line.trim()
  return t.length >= 4
    && t === t.toUpperCase()
    && /^[A-Z0-9 &/()\-'.]+$/.test(t)
    && !/^\d+\./.test(t)
}

function isClauseLine(line) {
  return /^\d+\.\s/.test(line.trim())
}

function isFieldLine(line) {
  return /^\s{2,}\S/.test(line) && /:\s*/.test(line.trim())
}

function parseAgreementBody(text) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const result = { title: '', subtitle: '', intro: [], sections: [], footer: null }
  let i = 0

  while (i < lines.length && !lines[i].trim()) i++
  if (i < lines.length) result.title = lines[i++].trim()
  while (i < lines.length && !lines[i].trim()) i++
  if (i < lines.length && lines[i].trim().startsWith('(')) {
    result.subtitle = lines[i++].trim()
  }

  let section = null
  let paragraph = []

  function flushParagraph() {
    const t = paragraph.join(' ').replace(/\s+/g, ' ').trim()
    paragraph = []
    if (!t) return
    if (section) section.content.push({ type: 'p', text: t })
    else result.intro.push(t)
  }

  function pushSection(title) {
    flushParagraph()
    if (section) result.sections.push(section)
    section = { title, content: [] }
  }

  for (; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()
    if (!trimmed) {
      flushParagraph()
      continue
    }

    if (trimmed.startsWith('- ')) {
      flushParagraph()
      result.footer = trimmed
      continue
    }

    if (isSectionHeader(line) && !isFieldLine(line)) {
      pushSection(trimmed)
      continue
    }

    if (isClauseLine(line)) {
      flushParagraph()
      if (!section) pushSection('Terms and conditions')
      const num = trimmed.match(/^(\d+)\./)[1]
      section.content.push({
        type: 'clause',
        num,
        text: trimmed.replace(/^\d+\.\s*/, ''),
      })
      continue
    }

    if (isFieldLine(line)) {
      flushParagraph()
      if (!section) pushSection('')
      const m = trimmed.match(/^([^:]+):\s*(.*)$/)
      if (m) {
        section.content.push({ type: 'field', label: m[1].trim(), value: m[2].trim() })
      }
      continue
    }

    if (section?.content.at(-1)?.type === 'field' && /^\s{2,}/.test(line) && !/:\s*/.test(trimmed)) {
      section.content.at(-1).value += (section.content.at(-1).value ? ' ' : '') + trimmed
      continue
    }

    if (section?.content.at(-1)?.type === 'clause' && /^\s{2,}/.test(line)) {
      section.content.at(-1).text += ' ' + trimmed
      continue
    }

    paragraph.push(trimmed)
  }

  flushParagraph()
  if (section) result.sections.push(section)
  return result
}

function AgreementDocument({ body }) {
  const doc = parseAgreementBody(body)

  return (
    <div className="agr-doc">
      {(doc.title || doc.subtitle) && (
        <div className="agr-intro">
          {doc.title && <h2 className="ob-h2">{doc.title}</h2>}
          {doc.subtitle && <p className="ob-p" style={{ color: 'var(--tx-2)', fontSize: 13 }}>{doc.subtitle}</p>}
        </div>
      )}

      {doc.intro.map((p, i) => (
        <p key={`intro-${i}`} className="ob-p">{p}</p>
      ))}

      {doc.sections.map((section, i) => (
        <div key={`${section.title}-${i}`} className="ob-section">
          {section.title && (
            <div className="ob-section-label">
              <span className="ob-section-tag">{section.title}</span>
            </div>
          )}
          <div className="ob-section-body">
            {section.content.map((block, j) => {
              if (block.type === 'p') {
                return <p key={j} className="ob-p" style={{ fontSize: 13 }}>{block.text}</p>
              }
              if (block.type === 'field') {
                return (
                  <div key={j} className="agr-field">
                    <span className="agr-field-label">{block.label}</span>
                    <span className="agr-field-value">{block.value || '—'}</span>
                  </div>
                )
              }
              if (block.type === 'clause') {
                return (
                  <div key={j} className="ob-clause">
                    <span className="ob-clause-n">{block.num}</span>
                    <div className="ob-clause-body">{block.text}</div>
                  </div>
                )
              }
              return null
            })}
          </div>
        </div>
      ))}

      {doc.footer && <p className="agr-foot">{doc.footer}</p>}
    </div>
  )
}

async function downloadAgreementPdf(kind, roundId) {
  const path = kind === 'master'
    ? '/api/agreement/master/download'
    : `/api/agreement/round/${roundId}/download`
  const name = kind === 'master'
    ? 'lotto-chee-group-prize-agreement.pdf'
    : `lotto-chee-round-${roundId}-agreement.pdf`

  // Build a self-authenticating URL with a one-time token so it works even when
  // opened in an external browser (Telegram) that has no session cookie.
  const base = import.meta.env.VITE_API_BASE ?? ''
  let url = base + path
  try {
    const { token } = await api.agreement.downloadToken()
    if (token) url += `?t=${encodeURIComponent(token)}`
  } catch { /* fall back to cookie auth on web */ }

  // Inside Telegram, hand the link to the system browser, which can save files
  // (the in-app webview cannot download).
  const tg = window.Telegram?.WebApp
  if (tg?.initData && typeof tg.openLink === 'function') {
    tg.openLink(url)
    return
  }

  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.rel = 'noopener'
  a.target = '_blank'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
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
        <div className="body">
          {err ? (
            <p style={{ fontSize: 14, color: 'var(--danger)' }}>{err}</p>
          ) : !doc ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}>
              <div className="spinner" />
            </div>
          ) : (
            <AgreementDocument body={doc.body} />
          )}
        </div>
        {doc && !err && (
          <div className="sheet-foot">
            <button type="button" className="btn btn-primary btn-block"
              disabled={downloading}
              onClick={onDownload}>
              {downloading ? 'Preparing PDF…' : 'Download PDF'}
            </button>
          </div>
        )}
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
          fontSize: 13, fontWeight: 600, opacity: disabled ? 0.65 : 1,
        }}>
        📄 {label}
      </button>
      {disabled && disabledHint && (
        <span style={{ fontSize: 12, color: 'var(--tx-3)', display: 'block', marginTop: 4 }}>
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
