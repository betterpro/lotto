import { useEffect, useRef, useState } from 'react'
import { LOGO_SRC } from '../brand.js'
import { api } from '../api.js'
import { INVITE_SLUG_KEY } from '../routes.js'

function pendingInviteSlug() {
  try { return localStorage.getItem(INVITE_SLUG_KEY) || undefined } catch { return undefined }
}

export default function Login({ onLogin }) {
  const widgetRef = useRef(null)
  const googleRef = useRef(null)
  const botUsername = import.meta.env.VITE_BOT_USERNAME

  const [mode, setMode] = useState('login') // 'login' | 'signup'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // ── Telegram Login Widget ────────────────────────────────────────────────
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

  // ── Google Identity Services button ──────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function mountGoogle() {
      let clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID
      if (!clientId) {
        try {
          const cfg = await api.auth.config()
          clientId = cfg.google_client_id
        } catch { /* ignore */ }
      }
      if (cancelled || !clientId || !googleRef.current) return

      const handleCredential = async (resp) => {
        try {
          await api.auth.google({ id_token: resp.credential, invite_slug: pendingInviteSlug() })
          if (!cancelled) onLogin()
        } catch (e) {
          setError(e.message || 'Google sign-in failed')
        }
      }

      const render = () => {
        if (cancelled || !window.google?.accounts?.id || !googleRef.current) return
        window.google.accounts.id.initialize({ client_id: clientId, callback: handleCredential })
        googleRef.current.innerHTML = ''
        window.google.accounts.id.renderButton(googleRef.current, {
          theme: 'outline', size: 'large', shape: 'pill', width: 280, text: 'continue_with',
        })
      }

      if (window.google?.accounts?.id) {
        render()
      } else {
        const existing = document.getElementById('gsi-script')
        if (existing) {
          existing.addEventListener('load', render, { once: true })
        } else {
          const script = document.createElement('script')
          script.id = 'gsi-script'
          script.src = 'https://accounts.google.com/gsi/client'
          script.async = true
          script.defer = true
          script.onload = render
          document.head.appendChild(script)
        }
      }
    }

    mountGoogle()
    return () => { cancelled = true }
  }, [onLogin])

  async function submitEmail(e) {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      const invite_slug = pendingInviteSlug()
      if (mode === 'signup') {
        await api.auth.signup({ name, email, password, invite_slug })
      } else {
        await api.auth.login({ email, password })
      }
      onLogin()
    } catch (err) {
      setError(err.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  const tgBot = botUsername ?? 'LottoCheeBot'

  return (
    <div style={{
      minHeight: 'var(--app-h)', background: '#fff', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box',
      padding: 'calc(28px + var(--sat)) calc(24px + var(--sar)) calc(28px + var(--sab)) calc(24px + var(--sal))',
      gap: 20, textAlign: 'center',
    }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ width: 96, height: 106, objectFit: 'contain' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span style={{ fontSize: 22, fontWeight: 800, color: '#111' }}>
          {mode === 'signup' ? 'Create your account' : 'Welcome back'}
        </span>
        <span style={{ fontSize: 14, color: '#666', lineHeight: 1.5, maxWidth: 320 }}>
          Pool tickets with friends and share the winnings.
        </span>
      </div>

      <form onSubmit={submitEmail} style={{ width: '100%', maxWidth: 320, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {mode === 'signup' && (
          <input
            type="text" placeholder="Name" value={name} autoComplete="name"
            onChange={e => setName(e.target.value)} style={inputStyle}
          />
        )}
        <input
          type="email" placeholder="Email" value={email} autoComplete="email" required
          onChange={e => setEmail(e.target.value)} style={inputStyle}
        />
        <input
          type="password" placeholder="Password" value={password} required
          autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
          onChange={e => setPassword(e.target.value)} style={inputStyle}
        />
        {error && <span style={{ fontSize: 13, color: 'var(--danger, #d33)' }}>{error}</span>}
        <button type="submit" className="primary" disabled={busy} style={{ padding: '12px 16px', fontSize: 15, fontWeight: 700, borderRadius: 12 }}>
          {busy ? 'Please wait…' : (mode === 'signup' ? 'Sign up' : 'Log in')}
        </button>
      </form>

      <button
        type="button"
        onClick={() => { setError(''); setMode(mode === 'signup' ? 'login' : 'signup') }}
        style={{ background: 'none', border: 'none', color: '#0a84ff', fontSize: 14, cursor: 'pointer' }}
      >
        {mode === 'signup' ? 'Already have an account? Log in' : "New here? Create an account"}
      </button>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', maxWidth: 320, color: '#bbb', fontSize: 12 }}>
        <div style={{ flex: 1, height: 1, background: '#eee' }} /> or <div style={{ flex: 1, height: 1, background: '#eee' }} />
      </div>

      <div ref={googleRef} style={{ minHeight: 40, display: 'flex', justifyContent: 'center' }} />
      <div ref={widgetRef} style={{ minHeight: 40 }} />

      <a
        href={`https://t.me/${tgBot}?startapp=open`}
        style={{ fontSize: 13, color: '#888', textDecoration: 'none' }}
      >
        Or open in Telegram →
      </a>
      <span style={{ fontSize: 12, color: '#bbb' }}>lottochee.com · with love and hope</span>
    </div>
  )
}

const inputStyle = {
  padding: '12px 14px', fontSize: 15, borderRadius: 12, border: '1px solid #ddd',
  outline: 'none', width: '100%', boxSizing: 'border-box', background: '#fafafa',
}
