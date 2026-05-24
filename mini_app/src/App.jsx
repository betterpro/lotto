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
import { LOGO_SRC, HOME_LOGO_SRC } from './brand.js'

const ONB_KEY = 'lottoo_beneficiary'

const TITLE = {
  home:    { t: 'Lotto Chee',   s: 'Group lotto · live'  },
  rounds:  { t: 'Rounds',   s: 'All draws'           },
  history: { t: 'Activity', s: 'Your account'        },
  profile: { t: 'Profile',  s: 'Settings & prefs'    },
  admin:   { t: 'Admin',    s: 'Trustee dashboard'   },
}

function TGHeader({ page }) {
  const logoSrc = page === 'home' ? HOME_LOGO_SRC : LOGO_SRC
  return (
    <header className="tg-header">
      <img src={logoSrc} alt="Lotto Chee" style={{ height: 44, objectFit: 'contain' }} />
      <div className="col" style={{ marginLeft: 10, gap: 1 }}>
        <span style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.25, color: 'var(--tx-1)' }}>Play together,</span>
        <span style={{ fontSize: 13, fontWeight: 700, lineHeight: 1.25, color: 'var(--tx-1)' }}>dream bigger</span>
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

  useEffect(() => {
    if (!user) return
    try {
      const raw = localStorage.getItem(ONB_KEY)
      if (raw) api.beneficiary.save(JSON.parse(raw)).catch(() => {})
    } catch { /* ignore */ }
  }, [user])

  if (error) {
    const notInTelegram = error.includes('X-Init-Data') || error.includes('initData') || error.includes('bot first')
    if (notInTelegram) {
      const botUsername = import.meta.env.VITE_BOT_USERNAME ?? 'LottoCheeBot'
      return (
        <div style={{ minHeight: '100dvh', background: '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 24px', gap: 28, textAlign: 'center' }}>
          <img src={LOGO_SRC} alt="Lotto Chee" style={{ width: 140, height: 154, objectFit: 'contain' }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <span style={{ fontSize: 24, fontWeight: 800, color: '#111' }}>Group Lottery, Together</span>
            <span style={{ fontSize: 15, color: '#666', lineHeight: 1.6, maxWidth: 280 }}>
              Pool tickets with friends and share the winnings — all inside Telegram.
            </span>
          </div>
          <a
            href={`https://t.me/${botUsername}?startapp=open`}
            style={{ display: 'inline-flex', alignItems: 'center', gap: 10, background: '#E8503A', color: '#fff', fontWeight: 700, fontSize: 17, padding: '16px 32px', borderRadius: 16, textDecoration: 'none', boxShadow: '0 4px 16px rgba(232,80,58,0.35)' }}
          >
            Open App in Telegram
          </a>
          <span style={{ fontSize: 12, color: '#bbb' }}>lottochee.com · BC, Canada</span>
        </div>
      )
    }
    return (
      <div className="center-screen" style={{ padding: 24 }}>
        <span style={{ fontSize: 48 }}>⚠️</span>
        <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--danger)' }}>{error}</span>
      </div>
    )
  }

  if (!user) return (
    <div className="center-screen">
      <div className="spinner" />
      <span style={{ fontSize: 13, color: 'var(--tx-2)' }}>Loading…</span>
    </div>
  )

  if (!onboarded) return (
    <Onboarding onAccept={(data) => {
      localStorage.setItem(ONB_KEY, JSON.stringify(data))
      api.beneficiary.save(data).catch(() => {})
      setOnboarded(true)
    }} />
  )

  const PAGES = { home: Home, rounds: Rounds, history: History, profile: Profile, admin: Admin }
  const Page  = PAGES[page] ?? Home

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
