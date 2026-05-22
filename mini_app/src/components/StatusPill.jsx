const CFG = {
  OPEN:     { label: 'OPEN',            cls: 'open',     dot: true  },
  CLOSING:  { label: 'CLOSING SOON',    cls: 'closing',  dot: false },
  UPLOADED: { label: 'TICKET UPLOADED', cls: 'uploaded', dot: false },
  DRAWN:    { label: 'DRAWN',           cls: 'drawn',    dot: false },
  // legacy fallbacks
  live:     { label: 'OPEN',            cls: 'open',     dot: true  },
  closing:  { label: 'CLOSING SOON',    cls: 'closing',  dot: false },
  done:     { label: 'DRAWN',           cls: 'drawn',    dot: false },
}

export function StatusPill({ status }) {
  const { label, cls, dot } = CFG[status] ?? { label: status, cls: 'drawn', dot: false }
  return (
    <span className={`status-pill ${cls}`}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }} />}
      {label}
    </span>
  )
}
