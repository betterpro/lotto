import { XIcon } from './Icon.jsx'

export function Sheet({ open, onClose, title, children }) {
  if (!open) return null
  return (
    <div className="sheet-overlay" onClick={onClose}>
      <div className="sheet" onClick={e => e.stopPropagation()}>
        <div className="handle" />
        <div className="sheet-head">
          <span className="sheet-title">{title}</span>
          <button className="sheet-close" onClick={onClose}>
            <XIcon width={14} height={14} />
          </button>
        </div>
        <div className="body">{children}</div>
      </div>
    </div>
  )
}
