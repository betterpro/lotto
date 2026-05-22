import { useState, useEffect } from 'react'
import { api } from './api.js'
import BottomNav       from './components/BottomNav.jsx'
import TelegramAvatar  from './components/TelegramAvatar.jsx'
import Home      from './pages/Home.jsx'
import Rounds    from './pages/Rounds.jsx'
import History   from './pages/History.jsx'
import Profile   from './pages/Profile.jsx'
import Admin     from './pages/Admin.jsx'
import Onboarding from './pages/Onboarding.jsx'

const ONB_KEY = 'lottoo_beneficiary'

const TITLE = {
  home:    { t: 'Lotto Chee',   s: 'Group lotto · live'  },
  rounds:  { t: 'Rounds',   s: 'All draws'           },
  history: { t: 'Activity', s: 'Your account'        },
  profile: { t: 'Profile',  s: 'Settings & prefs'    },
  admin:   { t: 'Admin',    s: 'Trustee dashboard'   },
}

function TGHeader({ page, user }) {
  const { t, s } = TITLE[page] ?? TITLE.home
  return (
    <header className="tg-header">
      <TelegramAvatar
        user={user}
        size={34}
        style={{ cursor: 'pointer' }}
        onClick={() => window.Telegram?.WebApp?.close()}
      />
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
        Open the bot first, then come back.
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

  const PAGES = { home: Home, rounds: Rounds, history: History, profile: Profile, admin: Admin }
  const Page  = PAGES[page] ?? Home

  return (
    <div className="app">
      <TGHeader page={page} user={user} />
      <div className="scroll">
        <Page user={user} onUserUpdate={setUser} />
      </div>
      <BottomNav page={page} setPage={setPage} isTrustee={!!user.is_trustee} />
    </div>
  )
}
