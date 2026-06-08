import { useEffect, useRef } from 'react'
import { LOGO_SRC } from '../brand.js'
import { api } from '../api.js'

export default function Login({ onLogin }) {
  const widgetRef = useRef(null)
  const botUsername = import.meta.env.VITE_BOT_USERNAME

  useEffect(() => {
    let cancelled = false

    window.onTelegramAuth = async (user) => {
      try {
        await api.auth.telegramLogin(user)
        if (!cancelled) onLogin()
      } catch (e) {
        alert(e.message || 'Login failed')
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

  const tgBot = botUsername ?? 'LottoCheeBot'

  return (
    <div style={{
      minHeight: 'var(--app-h)', background: '#fff', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box',
      padding: 'calc(32px + var(--sat)) calc(24px + var(--sar)) calc(32px + var(--sab)) calc(24px + var(--sal))',
      gap: 28, textAlign: 'center',
    }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ width: 140, height: 154, objectFit: 'contain' }} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <span style={{ fontSize: 24, fontWeight: 800, color: '#111' }}>Group Lottery, Together</span>
        <span style={{ fontSize: 15, color: '#666', lineHeight: 1.6, maxWidth: 320 }}>
          Pool tickets with friends and share the winnings. Sign in with Telegram to continue on the web.
        </span>
      </div>
      <div ref={widgetRef} style={{ minHeight: 48 }} />
      <a
        href={`https://t.me/${tgBot}?startapp=open`}
        style={{ fontSize: 14, color: '#888', textDecoration: 'none' }}
      >
        Or open in Telegram →
      </a>
      <span style={{ fontSize: 12, color: '#bbb' }}>lottochee.com · with love and hope</span>
    </div>
  )
}
