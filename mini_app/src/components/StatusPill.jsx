const CFG = {
  live:    { label: 'Live',    dot: true  },
  closing: { label: 'Closing', dot: false },
  done:    { label: 'Done',    dot: false },
}

export function StatusPill({ status }) {
  const { label, dot } = CFG[status] ?? { label: status, dot: false }
  return (
    <span className={`status-pill ${status ?? 'done'}`}>
      {dot && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }} />}
      {label}
    </span>
  )
}
