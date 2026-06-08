import { LOGO_SRC } from '../brand.js'

export default function NeedsInvite({ error }) {
  const botUsername = import.meta.env.VITE_BOT_USERNAME ?? 'LottoCheeBot'
  return (
    <div className="center-screen" style={{ gap: 20 }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ height: 56, objectFit: 'contain' }} />
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>You need a group invite</h2>
      {error && (
        <p style={{ fontSize: 13, color: 'var(--danger)', lineHeight: 1.5, maxWidth: 320, margin: 0 }}>
          {error}
        </p>
      )}
      <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, maxWidth: 320, margin: 0 }}>
        Ask your trustee to send you their group invite link, then open it in Telegram.
        New links open the app directly; older links start with{' '}
        <code style={{ fontSize: 12 }}>?start=g_…</code> — tap <strong>Start</strong> on the bot first, then open Lotto Chee.
      </p>
      <p style={{ fontSize: 13, color: 'var(--tx-3)', margin: 0 }}>
        Example: <code style={{ fontSize: 12 }}>t.me/{botUsername}?startapp=join_…</code>
      </p>
    </div>
  )
}
