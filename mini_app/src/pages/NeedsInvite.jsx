import { LOGO_SRC } from '../brand.js'

export default function NeedsInvite() {
  const botUsername = import.meta.env.VITE_BOT_USERNAME ?? 'LottoCheeBot'
  return (
    <div className="center-screen" style={{ padding: 24, textAlign: 'center', gap: 20 }}>
      <img src={LOGO_SRC} alt="Lotto Chee" style={{ height: 56, objectFit: 'contain' }} />
      <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>You need a group invite</h2>
      <p style={{ fontSize: 14, color: 'var(--tx-2)', lineHeight: 1.6, maxWidth: 320, margin: 0 }}>
        Ask your trustee to send you their group link. It looks like{' '}
        <code style={{ fontSize: 12 }}>t.me/{botUsername}?start=g_…</code>
      </p>
      <p style={{ fontSize: 13, color: 'var(--tx-3)', margin: 0 }}>
        Open that link in Telegram, then return here.
      </p>
    </div>
  )
}
