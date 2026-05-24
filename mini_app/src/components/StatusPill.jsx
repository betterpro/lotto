const CFG = {
  RALLY:    { label: 'Open',               cls: 'rally',    dot: true  },
  LOCKED:   { label: 'Waiting for draw',   cls: 'locked',   dot: false },
  REVEALED: { label: 'Drawn',              cls: 'revealed', dot: false },
  WON:      { label: 'Won',                cls: 'won',      dot: false },
  LOST:     { label: 'Lost',               cls: 'lost',     dot: false },
  // legacy
  OPEN:     { label: 'Open',               cls: 'rally',    dot: true  },
  CLOSING:  { label: 'Waiting for draw',   cls: 'locked',   dot: false },
  UPLOADED: { label: 'Waiting for draw',   cls: 'locked',   dot: false },
  DRAWN:    { label: 'Drawn',              cls: 'revealed', dot: false },
  live:     { label: 'Open',               cls: 'rally',    dot: true  },
  closing:  { label: 'Waiting for draw',   cls: 'locked',   dot: false },
  done:     { label: 'Drawn',              cls: 'revealed', dot: false },
}

export function StatusPill({ status }) {
  const { label, cls, dot } = CFG[status] ?? { label: status, cls: 'revealed', dot: false }
  return (
    <span className={`status-pill ${cls}`}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }} />}
      {label}
    </span>
  )
}
