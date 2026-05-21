const TABS = [
  { id: 'home',    icon: '🏠', label: 'Home'    },
  { id: 'round',   icon: '🎰', label: 'Round'   },
  { id: 'history', icon: '📋', label: 'History' },
  { id: 'admin',   icon: '👑', label: 'Admin'   },
]

export default function BottomNav({ page, setPage, isTrustee }) {
  const tabs = isTrustee ? TABS : TABS.filter(t => t.id !== 'admin')
  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      background: 'var(--bg2)', borderTop: '1px solid rgba(0,0,0,.06)',
      display: 'flex', padding: 'calc(8px) 0 calc(8px + env(safe-area-inset-bottom))',
      zIndex: 100,
    }}>
      {tabs.map(t => (
        <button key={t.id} onClick={() => setPage(t.id)} style={{
          flex: 1, background: 'none', border: 'none', cursor: 'pointer',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
          padding: '2px 0', color: page === t.id ? 'var(--btn)' : 'var(--hint)',
          transition: 'color .15s',
        }}>
          <span style={{ fontSize: 24 }}>{t.icon}</span>
          <span style={{ fontSize: 10, fontWeight: 600 }}>{t.label}</span>
        </button>
      ))}
    </nav>
  )
}
