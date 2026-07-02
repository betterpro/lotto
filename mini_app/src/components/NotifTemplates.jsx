import { useState, useEffect, useCallback } from 'react'
import { useToast } from './Toast'

/**
 * Editable Telegram notification templates with a dynamic-data guide.
 *
 * Props:
 *   load(): Promise<{templates}>       — fetch the template list
 *   save(key, text, reset): Promise    — persist / reset one template
 *   test(key, text): Promise           — send a sample to the caller's Telegram
 *   intro: string                      — short blurb shown at the top
 */
export default function NotifTemplates({ load, save, test, intro }) {
  const showToast = useToast()
  const [items, setItems] = useState(null)
  const [edits, setEdits] = useState({})
  const [busy, setBusy] = useState({})
  const [openGuide, setOpenGuide] = useState({})

  const reload = useCallback(
    () => load().then(r => setItems(r.templates || [])).catch(e => showToast(e.message, 'error')),
    [load, showToast],
  )
  useEffect(() => { reload() }, [reload])

  const setB = (k, v) => setBusy(p => ({ ...p, [k]: v }))
  const clearEdit = (key) => setEdits(p => { const n = { ...p }; delete n[key]; return n })

  async function doSave(t) {
    setB(t.key, true)
    try {
      await save(t.key, edits[t.key] ?? t.text)
      showToast('Saved', 'success'); clearEdit(t.key); await reload()
    } catch (e) { showToast(e.message, 'error') } finally { setB(t.key, false) }
  }
  async function doReset(t) {
    setB(t.key, true)
    try {
      await save(t.key, '', true)
      showToast('Reset to default', 'success'); clearEdit(t.key); await reload()
    } catch (e) { showToast(e.message, 'error') } finally { setB(t.key, false) }
  }
  async function doTest(t) {
    setB(t.key + '_t', true)
    try {
      await test(t.key, edits[t.key] ?? t.text)
      showToast('Test sent to your Telegram', 'success')
    } catch (e) { showToast(e.message, 'error') } finally { setB(t.key + '_t', false) }
  }

  if (!items) return <div style={{ padding: 40, display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
  return (
    <div className="stack">
      <p style={{ padding: '0 16px', fontSize: 13, color: 'var(--tx-3)', lineHeight: 1.5 }}>
        {intro || (
          <>Edit the bot’s Telegram messages. Keep the <span className="mono">{'{placeholders}'}</span> for dynamic values
            and use <span className="mono">&lt;b&gt;…&lt;/b&gt;</span> for bold. “Send test” delivers a sample to your own Telegram.</>
        )}
      </p>
      {items.map(t => {
        const val = edits[t.key] ?? t.text
        const dirty = edits[t.key] !== undefined && edits[t.key] !== t.text
        const vars = t.vars || []
        const guideOpen = openGuide[t.key]
        return (
          <div key={t.key} className="card col gap-8" style={{ padding: 14 }}>
            <div className="row between" style={{ alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>{t.label}</span>
              {t.overridden && <span className="chip chip-gold" style={{ fontSize: 11, padding: '2px 8px' }}>custom</span>}
            </div>
            <span style={{ fontSize: 12.5, color: 'var(--tx-3)', lineHeight: 1.4 }}>{t.desc}</span>
            <textarea className="input" rows={5} value={val}
              onChange={e => setEdits(p => ({ ...p, [t.key]: e.target.value }))}
              style={{ fontFamily: 'var(--mono)', fontSize: 13, lineHeight: 1.5, resize: 'vertical' }} />

            {vars.length > 0 && (
              <div style={{ borderTop: '1px solid var(--bd)', paddingTop: 8 }}>
                <button type="button" onClick={() => setOpenGuide(p => ({ ...p, [t.key]: !p[t.key] }))}
                  style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                    color: 'var(--tx-2)', fontSize: 12.5, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>{guideOpen ? '▾' : '▸'}</span>
                  Dynamic data you can use ({vars.length})
                </button>
                {guideOpen && (
                  <div className="col gap-4" style={{ marginTop: 8 }}>
                    {vars.map(v => (
                      <div key={v.name} className="row gap-8" style={{ alignItems: 'baseline', fontSize: 12.5, lineHeight: 1.4 }}>
                        <span className="mono" style={{ color: 'var(--gold, #c8a24a)', flexShrink: 0 }}>{`{${v.name}}`}</span>
                        <span style={{ color: 'var(--tx-3)' }}>{v.help || '—'}</span>
                      </div>
                    ))}
                    <p style={{ fontSize: 11.5, color: 'var(--tx-3)', marginTop: 4, lineHeight: 1.4 }}>
                      Insert a placeholder exactly as shown, e.g. <span className="mono">{'{rid}'}</span>, and it’s
                      replaced with the live value when the message is sent. Missing ones are simply left blank.
                    </p>
                  </div>
                )}
              </div>
            )}

            <div className="row gap-8">
              <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} disabled={busy[t.key + '_t']} onClick={() => doTest(t)}>
                {busy[t.key + '_t'] ? '…' : '📤 Send test'}
              </button>
              <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} disabled={busy[t.key] || !t.overridden} onClick={() => doReset(t)}>
                Reset
              </button>
              <button className="btn btn-primary btn-sm" style={{ flex: 1 }} disabled={busy[t.key] || !dirty} onClick={() => doSave(t)}>
                {busy[t.key] ? '…' : 'Save'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
