import { useState, useEffect } from 'react'
import { api } from './api.js'
import BottomNav from './components/BottomNav.jsx'
import Home    from './pages/Home.jsx'
import Round   from './pages/Round.jsx'
import History from './pages/History.jsx'
import Admin   from './pages/Admin.jsx'

export default function App() {
  const [page, setPage]   = useState('home')
  const [user, setUser]   = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => { api.me().then(setUser).catch(e => setError(e.message)) }, [])

  if (error) return (
    <div className="center-screen">
      <div style={{ fontSize: 48 }}>⚠️</div>
      <p className="error-text">{error}</p>
      <p className="hint">Open @Lottoomax_bot first, then come back.</p>
    </div>
  )

  if (!user) return <div className="center-screen"><div className="spinner" /></div>

  const PAGES = { home: Home, round: Round, history: History, admin: Admin }
  const Page  = PAGES[page]

  return (
    <div className="app">
      <Page user={user} onUserUpdate={setUser} />
      <BottomNav page={page} setPage={setPage} isTrustee={user.is_trustee} />
    </div>
  )
}
