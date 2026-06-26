import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo.jsx'
import { api, setAccessToken } from '../api.js'
import { initAuthSession } from '../authSession.js'
import { INVITE_SLUG_KEY } from '../routes.js'

function pendingInviteSlug() {
  try { return localStorage.getItem(INVITE_SLUG_KEY) || undefined } catch { return undefined }
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  )
}

function AppleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M17.05 20.28c-.98.95-2.05 1.88-3.71 1.88-1.66 0-2.19-.99-4.09-.99-1.9 0-2.49.96-4.08.99-1.58.03-2.78-1.41-3.76-2.36C2.79 17.25 1.14 12.45 3.07 9.3c.96-1.66 2.7-2.71 4.58-2.74 1.8-.03 3.5 1.2 4.09 1.2.59 0 2.4-1.48 4.05-1.26.69.03 2.63.28 3.87 2.1-3.25 1.77-2.73 6.38.52 7.87-.63 1.62-1.45 3.23-2.83 4.81zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
    </svg>
  )
}

export default function Login({ onLogin }) {
  const widgetRef = useRef(null)
  const botUsername = import.meta.env.VITE_BOT_USERNAME
  const oauthHandled = useRef(false)

  const [mode, setMode] = useState('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [supabaseReady, setSupabaseReady] = useState(false)
  const [supabase, setSupabase] = useState(null)

  const completeAuth = useCallback(async (client) => {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) throw new Error('No active session')
    setAccessToken(session.access_token)
    await api.auth.sync({ invite_slug: pendingInviteSlug() })
    onLogin()
  }, [onLogin])

  useEffect(() => {
    let cancelled = false
    initAuthSession().then(async (client) => {
      if (cancelled) return
      setSupabase(client)
      setSupabaseReady(!!client)
      if (!client || oauthHandled.current) return
      const { data: { session } } = await client.auth.getSession()
      if (!session) return
      oauthHandled.current = true
      setBusy(true)
      try {
        await completeAuth(client)
      } catch (e) {
        setError(e.message || 'Could not finish sign-in')
      } finally {
        if (!cancelled) setBusy(false)
      }
    })
    return () => { cancelled = true }
  }, [completeAuth])

  useEffect(() => {
    let cancelled = false
    window.onTelegramAuth = async (user) => {
      try {
        await api.auth.telegramLogin(user)
        if (!cancelled) onLogin()
      } catch (e) {
        setError(e.message || 'Login failed')
      }
    }

    async function mountWidget() {
      let username = botUsername
      if (!username) {
        try {
          const cfg = await api.auth.config()
          username = cfg.bot_username
        } catch { /* ignore */ }
      }
      if (cancelled || !username || !widgetRef.current) return
      widgetRef.current.innerHTML = ''
      const script = document.createElement('script')
      script.src = 'https://telegram.org/js/telegram-widget.js?22'
      script.async = true
      script.setAttribute('data-telegram-login', username)
      script.setAttribute('data-size', 'large')
      script.setAttribute('data-radius', '12')
      script.setAttribute('data-onauth', 'onTelegramAuth(user)')
      widgetRef.current.appendChild(script)
    }

    mountWidget()
    return () => {
      cancelled = true
      delete window.onTelegramAuth
    }
  }, [botUsername, onLogin])

  const signInWithOAuth = useCallback(async (provider) => {
    if (!supabase) {
      setError('Web sign-in is not configured yet')
      return
    }
    setError('')
    setBusy(true)
    try {
      const { error: oauthError } = await supabase.auth.signInWithOAuth({
        provider,
        options: { redirectTo: `${window.location.origin}/login` },
      })
      if (oauthError) throw oauthError
    } catch (e) {
      setError(e.message || `${provider} sign-in failed`)
      setBusy(false)
    }
  }, [supabase])

  async function submitEmail(e) {
    e.preventDefault()
    if (!supabase) {
      setError('Web sign-in is not configured yet')
      return
    }
    setError('')
    setBusy(true)
    try {
      if (mode === 'signup') {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: name.trim() || email.split('@')[0] } },
        })
        if (signUpError) throw signUpError
        if (data.session) {
          await completeAuth(supabase)
        } else {
          setError('Check your email to confirm your account, then log in.')
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password })
        if (signInError) throw signInError
        await completeAuth(supabase)
      }
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const tgBot = botUsername ?? 'LottoCheeBot'
  const showOAuth = supabaseReady

  return (
    <div className="login-page">
      <div className="login-panel">
        <Link to="/" className="login-brand">
          <Logo size={60} wordmark fontSize={38} />
        </Link>

        <div className="login-intro">
          <h1 className="login-title">
            {mode === 'signup' ? 'Create your account' : 'Welcome back'}
          </h1>
          <p className="login-intro-sub">
            Pool tickets with friends and share the winnings.
          </p>
        </div>

        {!supabaseReady && (
          <p className="login-warn">
            Email and social sign-in need Supabase Auth configured. Add SUPABASE_ANON_KEY to your environment.
          </p>
        )}

        {showOAuth && (
          <div className="oauth-stack login-oauth">
            <button type="button" className="oauth-btn" disabled={busy} onClick={() => signInWithOAuth('google')}>
              <GoogleIcon />
              <span>Continue with Google</span>
            </button>
            <button type="button" className="oauth-btn" disabled={busy} onClick={() => signInWithOAuth('apple')}>
              <AppleIcon />
              <span>Continue with Apple</span>
            </button>
          </div>
        )}

        {showOAuth && (
          <div className="oauth-divider login-divider">
            <div /> or <div />
          </div>
        )}

        <form onSubmit={submitEmail} className="login-form">
          {mode === 'signup' && (
            <input
              type="text" placeholder="Name" value={name} autoComplete="name"
              onChange={e => setName(e.target.value)} className="input"
            />
          )}
          <input
            type="email" placeholder="Email" value={email} autoComplete="email" required
            onChange={e => setEmail(e.target.value)} className="input"
          />
          <input
            type="password" placeholder="Password" value={password} required minLength={8}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            onChange={e => setPassword(e.target.value)} className="input"
          />
          {error && <span className="login-error">{error}</span>}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !supabaseReady}>
            {busy ? 'Please wait…' : (mode === 'signup' ? 'Sign up with email' : 'Log in with email')}
          </button>
        </form>

        <button
          type="button"
          className="login-mode-toggle"
          onClick={() => { setError(''); setMode(mode === 'signup' ? 'login' : 'signup') }}
        >
          {mode === 'signup' ? 'Already have an account? Log in' : "New here? Create an account"}
        </button>

        <div className="oauth-divider login-divider">
          <div /> or <div />
        </div>

        <div ref={widgetRef} className="login-widget" />

        <div className="login-footer">
          <a href={`https://t.me/${tgBot}?startapp=open`} className="login-telegram">
            Or open in Telegram →
          </a>
          <span className="login-tagline">lottochee.com · with love and hope</span>
        </div>
      </div>
    </div>
  )
}
