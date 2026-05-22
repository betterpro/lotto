import { useState, useEffect } from 'react'
import { api } from './api.js'
import BottomNav from './components/BottomNav.jsx'
import Home    from './pages/Home.jsx'
import Round   from './pages/Round.jsx'
import History from './pages/History.jsx'
import Admin   from './pages/Admin.jsx'
import Onboarding from './pages/Onboarding.jsx'

const ONB_KEY = 'lottoo_beneficiary'

const TITLE = {
  home:    { t: 'LOTTOO',   s: 'Group lotto · live'  },
  round:   { t: 'Rounds',   s: 'All draws'           },
  history: { t: 'Activity', s: 'Your account'        },
  admin:   { t: 'Admin',    s: 'Trustee dashboard'   },
}

function TGHeader({ page }) {
  const { t, s } = TITLE[page] ?? TITLE.home
  return (
    <header className="tg-header">
      <div className="logo" onClick={() => window.Telegram?.WebApp?.close()}>L</div>
      <div className="col gap-4 grow">
        <span className="hd-title">{t}</span>
        <span className="hd-sub">{s}</span>
      </div>
    </header>
  )
}

export default function App() {
  const [page, setPage]   = useState('home')
  const [user, setUser]   = useState(null)
  const [error, setError] = useState(null)
  const [onboarded, setOnboarded] = useState(() => !!localStorage.getItem(ONB_KEY))

  useEffect(() => {
    window.Telegram?.WebApp?.ready()
    window.Telegram?.WebApp?.expand()
    api.me().then(setUser).catch(e => setError(e.message))
  }, [])

  if (error) return (
    <div className="center-screen" style={{ padding: 24 }}>
      <span style={{ fontSize: 48 }}>⚠️</span>
      <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--danger)' }}>{error}</span>
      <span style={{ fontSize: 13, color: 'var(--tx-2)', textAlign: 'center' }}>
        Open @Lottoomax_bot first, then come back.
      </span>
    </div>
  )

  if (!user) return (
    <div className="center-screen">
      <div className="spinner" />
      <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Loading…</span>
    </div>
  )

  if (!onboarded) return (
    <Onboarding onAccept={(data) => {
      localStorage.setItem(ONB_KEY, JSON.stringify(data))
      setOnboarded(true)
    }} />
  )

  const PAGES = { home: Home, round: Round, history: History, admin: Admin }
  const Page  = PAGES[page]

  return (
    <div className="app">
      <TGHeader page={page} />
      <div className="scroll">
        <Page user={user} onUserUpdate={setUser} />
      </div>
      <BottomNav page={page} setPage={setPage} isTrustee={!!user.is_trustee} />
    </div>
  )
}
