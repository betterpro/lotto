import { useNavigate } from 'react-router-dom'
import { LOGO_SRC } from '../brand.js'

const STEPS = [
  { n: '1', title: 'Join a group', body: 'Get a join code from a friend who runs a pool, or start your own.' },
  { n: '2', title: 'Chip in for tickets', body: 'Add a few dollars to the pool. Your trustee buys real BCLC tickets for the group.' },
  { n: '3', title: 'Win together', body: 'If a pooled ticket wins, the prize is split by everyone’s share — automatically.' },
]

const FEATURES = [
  ['🎟️', 'Real tickets', 'Every round is backed by official BCLC Lotto Max & 6/49 tickets — photos attached so you can check.'],
  ['🤝', 'Shared odds', 'Pooling means more tickets and better odds than playing alone. Bigger together.'],
  ['📊', 'Fully transparent', 'See the pool, every participant’s share, the ticket numbers and a signed agreement for each round.'],
]

export default function Landing() {
  const navigate = useNavigate()
  const goLogin = () => navigate('/login')

  return (
    <div style={{
      minHeight: 'var(--app-h)', background: '#fff', color: '#111',
      overflowY: 'auto', boxSizing: 'border-box',
      padding: 'calc(28px + var(--sat)) calc(20px + var(--sar)) calc(28px + var(--sab)) calc(20px + var(--sal))',
    }}>
      <div style={{ maxWidth: 440, margin: '0 auto', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>

        {/* Hero */}
        <img src={LOGO_SRC} alt="Lotto Chee" style={{ width: 92, height: 102, objectFit: 'contain', marginBottom: 16 }} />
        <h1 style={{ fontSize: 30, fontWeight: 800, margin: 0, textAlign: 'center', letterSpacing: '-.5px' }}>
          Play together,<br />dream bigger
        </h1>
        <p style={{ fontSize: 16, color: '#555', lineHeight: 1.55, textAlign: 'center', margin: '12px 0 0', maxWidth: 360 }}>
          Lotto Chee lets you pool lottery tickets with friends and share the winnings — real BCLC
          tickets, transparent pools, no spreadsheets.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: '100%', maxWidth: 320, marginTop: 24 }}>
          <button type="button" className="primary" onClick={goLogin}
            style={{ padding: '14px 16px', fontSize: 17, fontWeight: 700, borderRadius: 12, width: '100%' }}>
            Get started
          </button>
          <button type="button" onClick={goLogin}
            style={{ background: 'none', border: 'none', color: '#0a84ff', fontSize: 15, fontWeight: 600, cursor: 'pointer', padding: 6 }}>
            I already have an account · Log in
          </button>
        </div>

        {/* How it works */}
        <div style={{ width: '100%', marginTop: 40 }}>
          <h2 style={{ fontSize: 13, fontWeight: 700, letterSpacing: '.6px', textTransform: 'uppercase', color: '#999', textAlign: 'center', margin: '0 0 16px' }}>
            How it works
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {STEPS.map(s => (
              <div key={s.n} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
                <div style={{
                  flexShrink: 0, width: 32, height: 32, borderRadius: '50%',
                  background: '#eef5ff', color: '#0a84ff', fontWeight: 800, fontSize: 15,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>{s.n}</div>
                <div>
                  <div style={{ fontSize: 16, fontWeight: 700 }}>{s.title}</div>
                  <div style={{ fontSize: 14, color: '#666', lineHeight: 1.5, marginTop: 2 }}>{s.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Features */}
        <div style={{ width: '100%', marginTop: 36, display: 'flex', flexDirection: 'column', gap: 12 }}>
          {FEATURES.map(([icon, title, body]) => (
            <div key={title} style={{
              display: 'flex', gap: 14, alignItems: 'flex-start',
              background: '#f7f8fa', borderRadius: 14, padding: '14px 16px',
            }}>
              <span style={{ fontSize: 22, lineHeight: '26px' }}>{icon}</span>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700 }}>{title}</div>
                <div style={{ fontSize: 14, color: '#666', lineHeight: 1.5, marginTop: 2 }}>{body}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <button type="button" className="primary" onClick={goLogin}
          style={{ padding: '14px 16px', fontSize: 17, fontWeight: 700, borderRadius: 12, width: '100%', maxWidth: 320, marginTop: 32 }}>
          Get started — it’s free to join
        </button>

        <p style={{ fontSize: 13, color: '#aaa', textAlign: 'center', lineHeight: 1.6, margin: '20px 0 0' }}>
          Must be 19+ and located in British Columbia to participate.<br />
          lottochee.com · with love and hope
        </p>
      </div>
    </div>
  )
}
