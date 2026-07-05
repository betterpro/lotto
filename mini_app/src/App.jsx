import { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from './api.js'
import BottomNav       from './components/BottomNav.jsx'
import { LOGO_SRC, HOME_LOGO_SRC } from './brand.js'
import { APP_VERSION } from './version.js'
import { initAuthSession } from './authSession.js'
import {
  INVITE_SLUG_KEY,
  PAGE_PATHS,
  parseInviteSlug,
  pathToPage,
  isTelegram,
} from './routes.js'

const ONB_KEY = 'lottoo_beneficiary'

const Home = lazy(() => import('./pages/Home.jsx'))
const Rounds = lazy(() => import('./pages/Rounds.jsx'))
const History = lazy(() => import('./pages/History.jsx'))
const Profile = lazy(() => import('./pages/Profile.jsx'))
const TopUp = lazy(() => import('./pages/TopUp.jsx'))
const Admin = lazy(() => import('./pages/Admin.jsx'))
const PlatformAdmin = lazy(() => import('./pages/PlatformAdmin.jsx'))
const Onboarding = lazy(() => import('./pages/Onboarding.jsx'))
const NeedsInvite = lazy(() => import('./pages/NeedsInvite.jsx'))
const Login = lazy(() => import('./pages/Login.jsx'))
const Landing = lazy(() => import('./pages/Landing.jsx'))

function ScreenLoader({ label = 'Loading...' }) {
  return (
    <div className="center-screen">
      <div className="spinner" />
      <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>{label}</span>
    </div>
  )
}

function TGHeader({ page }) {
  const logoSrc = page === 'home' ? HOME_LOGO_SRC : LOGO_SRC
  return (
    <header className="tg-header">
      <img src={logoSrc} alt="LottoChee" className="tg-header-logo" />
      <div className="col tg-header-tagline">
        <span>Play together,</span>
        <span>dream bigger</span>
      </div>
      <span className="tg-header-version">v{APP_VERSION}</span>
    </header>
  )
}

function JoinRedirect() {
  const { slug } = useParams()
  useEffect(() => {
    if (slug) localStorage.setItem(INVITE_SLUG_KEY, slug)
  }, [slug])
  return <Navigate to="/" replace />
}

function AppShell({ user, onUserUpdate, loadUser, inviteSlug }) {
  const location = useLocation()
  const navigate = useNavigate()
  const page = pathToPage(location.pathname) ?? 'home'

  useEffect(() => {
    if (location.pathname !== '/' && !pathToPage(location.pathname)) {
      navigate('/', { replace: true })
    }
  }, [location.pathname, navigate])

  useEffect(() => {
    if (page === 'admin' && !user.is_group_trustee) navigate('/', { replace: true })
    if (page === 'platform' && !user.is_platform_admin) navigate('/', { replace: true })
  }, [page, user.is_group_trustee, user.is_platform_admin, navigate])

  const goTo = (p) => navigate(PAGE_PATHS[p] ?? '/')

  return (
    <div className="app">
      <TGHeader page={page} />
      <div className="scroll">
        <Suspense fallback={<ScreenLoader />}>
          <Routes>
            <Route path="/" element={<Home user={user} onUserUpdate={onUserUpdate} />} />
            <Route path="/topup" element={<TopUp user={user} onUserUpdate={onUserUpdate} />} />
            <Route path="/rounds" element={<Rounds user={user} />} />
            <Route path="/activity" element={<History user={user} />} />
            <Route path="/profile" element={<Profile user={user} onUserUpdate={onUserUpdate} />} />
            <Route path="/admin" element={<Admin user={user} />} />
            <Route path="/platform" element={<PlatformAdmin user={user} />} />
          </Routes>
        </Suspense>
      </div>
      <BottomNav
        page={page}
        setPage={goTo}
        isGroupTrustee={!!user.is_group_trustee}
        isPlatformAdmin={!!user.is_platform_admin}
      />
    </div>
  )
}

export default function App() {
  const location = useLocation()
  const [user, setUser]   = useState(null)
  const [error, setError] = useState(null)
  const [onboarded, setOnboarded] = useState(() => !!localStorage.getItem(ONB_KEY))
  const [inviteSlug] = useState(() => parseInviteSlug(location.pathname, location.search))
  const [inviteJoinError, setInviteJoinError] = useState(null)
  const inviteJoinAttempted = useRef(false)

  const loadUser = useCallback(() => {
    setInviteJoinError(null)
    setError(null)
    setUser(null)
    api.me()
      .then(setUser)
      .catch(e => setError(e.message || 'Could not load app'))
  }, [])

  useEffect(() => {
    if (inviteSlug) localStorage.setItem(INVITE_SLUG_KEY, inviteSlug)
    initAuthSession().finally(() => loadUser())
  }, [loadUser, inviteSlug])

  useEffect(() => {
    if (!user) return
    try {
      const raw = localStorage.getItem(ONB_KEY)
      if (raw) api.beneficiary.save(JSON.parse(raw)).catch(() => {})
    } catch { /* ignore */ }
  }, [user])

  useEffect(() => {
    if (!user?.needs_invite || !inviteSlug || inviteJoinAttempted.current) return
    inviteJoinAttempted.current = true
    let cancelled = false
    api.group.join(inviteSlug)
      .then(() => {
        if (!cancelled) {
          localStorage.removeItem(INVITE_SLUG_KEY)
          loadUser()
        }
      })
      .catch(e => {
        if (!cancelled) setInviteJoinError(e.message || 'Could not join group')
      })
    return () => { cancelled = true }
  }, [user?.needs_invite, inviteSlug, loadUser])

  if (error) {
    const needsLogin = !isTelegram() && (
      error.includes('Not authenticated') ||
      error.includes('Session expired') ||
      error.includes('X-Init-Data') ||
      error.includes('initData')
    )
    if (needsLogin) {
      if (location.pathname === '/login') {
        return (
          <Suspense fallback={<ScreenLoader />}>
            <Login onLogin={loadUser} />
          </Suspense>
        )
      }
      // Invite recipients go straight to sign-in so they can join the group;
      // everyone else lands on the marketing page first.
      if (inviteSlug) return <Navigate to="/login" replace />
      return (
        <Suspense fallback={<ScreenLoader />}>
          <Landing />
        </Suspense>
      )
    }
    return (
      <div className="center-screen">
        <span style={{ fontSize: 48 }}>⚠️</span>
        <span style={{ fontSize: 19, fontWeight: 700, color: 'var(--danger)' }}>{error}</span>
        <button className="primary" onClick={loadUser} style={{ marginTop: 12 }}>
          Try again
        </button>
      </div>
    )
  }

  if (!user) return (
    <div className="center-screen">
      <div className="spinner" />
      <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>Loading…</span>
    </div>
  )

  if (user.needs_invite) {
    if (inviteSlug && !inviteJoinError) {
      return (
        <div className="center-screen">
          <div className="spinner" />
          <span style={{ fontSize: 14, color: 'var(--tx-2)' }}>Joining your group…</span>
        </div>
      )
    }
    return (
      <Suspense fallback={<ScreenLoader />}>
        <NeedsInvite error={inviteJoinError} onJoined={loadUser} />
      </Suspense>
    )
  }

  const serverOnboarded = user.onboarded || !!user.agreement_accepted_at
  if (!onboarded && !serverOnboarded) return (
    <Suspense fallback={<ScreenLoader />}>
      <Onboarding
        user={user}
        group={user.group}
        trustee={user.trustee}
        inviteSlug={inviteSlug}
        onAccept={(data) => {
          localStorage.setItem(ONB_KEY, JSON.stringify(data))
          localStorage.removeItem(INVITE_SLUG_KEY)
          api.beneficiary.save(data).then(() => loadUser()).catch(() => {})
          setOnboarded(true)
        }}
      />
    </Suspense>
  )

  return (
    <Suspense fallback={<ScreenLoader />}>
      <Routes>
        <Route path="/join/:slug" element={<JoinRedirect />} />
        <Route path="/*" element={
          <AppShell user={user} onUserUpdate={setUser} loadUser={loadUser} inviteSlug={inviteSlug} />
        } />
      </Routes>
    </Suspense>
  )
}
