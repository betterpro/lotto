import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Logo, { LogoMark } from '../components/Logo.jsx'
import './landing.css'

const Arrow = (p) => (
  <svg width={p.s || 16} height={p.s || 16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
)
const TgIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M21.7 3.3 2.5 10.8c-1 .4-1 1.8 0 2.1l4.8 1.5 1.8 5.6c.3.9 1.4 1.1 2 .4l2.6-2.7 4.6 3.4c.7.5 1.7.1 1.9-.7L23.9 4.5c.2-1-.8-1.7-1.7-1.2Z" /></svg>
)
const WebIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M3 12h18" /><path d="M12 3a15 15 0 0 1 0 18 15 15 0 0 1 0-18" /></svg>
)
const Check = () => (
  <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M20 6 9 17l-5-5" /></svg>
)

export default function Landing() {
  const navigate = useNavigate()
  const go = () => navigate('/login')
  const [drawer, setDrawer] = useState(false)
  const closeDrawer = () => setDrawer(false)

  return (
    <div className="lcl">
      {/* ── NAV ── */}
      <nav className="nav">
        <div className="wrap nav-in">
          <a className="brand" href="#top" onClick={e => { e.preventDefault() }}>
            <LogoMark size={30} />
            <div className="brand-name">LottoChee</div>
          </a>
          <div className="nav-links">
            <a href="#how">How it works</a>
            <a href="#groups">Groups</a>
            <a href="#odds">The odds</a>
            <a href="#plans">Plans</a>
            <a href="#trust">Transparency</a>
            <a href="#faq">FAQ</a>
          </div>
          <div className="nav-cta">
            <a className="nav-login" onClick={go}>Sign in</a>
            <a className="btn btn-tg" onClick={go}>Get started <Arrow /></a>
          </div>
          <button className="nav-burger" type="button" aria-label="Open menu" onClick={() => setDrawer(true)}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
        </div>
      </nav>
      <span id="top" />

      {/* Mobile drawer */}
      <div className={'drawer' + (drawer ? ' open' : '')} onClick={closeDrawer}>
        <div className="drawer-panel" onClick={e => e.stopPropagation()}>
          <div className="drawer-head">
            <a className="brand" onClick={closeDrawer}><LogoMark size={28} /><div className="brand-name">LottoChee</div></a>
            <button className="drawer-close" type="button" aria-label="Close menu" onClick={closeDrawer}>✕</button>
          </div>
          <nav className="drawer-links">
            <a href="#how" onClick={closeDrawer}>How it works <span className="ar">→</span></a>
            <a href="#groups" onClick={closeDrawer}>Groups <span className="ar">→</span></a>
            <a href="#odds" onClick={closeDrawer}>The odds <span className="ar">→</span></a>
            <a href="#plans" onClick={closeDrawer}>Plans <span className="ar">→</span></a>
            <a href="#trust" onClick={closeDrawer}>Transparency <span className="ar">→</span></a>
            <a href="#faq" onClick={closeDrawer}>FAQ <span className="ar">→</span></a>
          </nav>
          <div className="drawer-cta">
            <a className="btn btn-tg btn-lg" onClick={() => { closeDrawer(); go() }}>Get started</a>
            <a className="btn btn-ghost btn-lg" onClick={() => { closeDrawer(); go() }}>Sign in</a>
          </div>
        </div>
      </div>

      {/* ── HERO ── */}
      <header className="hero">
        <div className="wrap hero-grid">
          <div className="hero-copy">
            <div className="hero-eyebrow-row">
              <span className="eyebrow"><span className="dot live" />Official lottery tickets</span>
              <span className="chip"><span className="ic"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg></span>Lotto Max · 6/49 · Daily Grand</span>
            </div>
            <h1 className="display">Play Canada's biggest draws. <span className="accentword">Together.</span></h1>
            <p className="lede">LottoChee pools your group into official lottery tickets — Lotto&nbsp;Max, Lotto&nbsp;6/49 and Daily&nbsp;Grand. Buy a share from $3, the pool buys the tickets, and every prize is split by your share — automatically. On Telegram or the web.</p>

            <div className="hero-games">
              <span className="games-label">Pooling every major draw</span>
              <div className="games-logos">
                <img className="game-logo" src="/logos/lotto_max.png" alt="Lotto Max" />
                <img className="game-logo" src="/logos/649.png" alt="Lotto 6/49" />
                <img className="game-logo" src="/logos/DG.png" alt="Daily Grand" />
              </div>
            </div>

            <div className="hero-cta">
              <a className="btn btn-tg btn-lg" onClick={go}>Get started <Arrow s={17} /></a>
              <a className="btn btn-ghost btn-lg" href="#how">See how it works
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 5v14M6 13l6 6 6-6" /></svg>
              </a>
            </div>

            <div className="channels">
              <span className="channels-label">Two ways to play —</span>
              <span className="channel"><TgIcon />Telegram</span>
              <span className="channel"><WebIcon />Web app</span>
            </div>

            <div className="hero-trust">
              <span className="trust-item"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m4 7 8-4 8 4v5c0 5-3.4 7.7-8 9-4.6-1.3-8-4-8-9V7Z" /><path d="m9 12 2 2 4-4" /></svg>Every ticket photographed</span>
              <span className="trust-item"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h18M12 3v18" /></svg>Prizes auto-split by share</span>
              <span className="trust-item"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 8v4l2 2" /></svg>19+ · Canada</span>
            </div>

            <div className="hero-stats">
              <div className="hstat"><div className="v tnum">3</div><div className="k">National draws pooled</div></div>
              <div className="hstat"><div className="v tnum"><span className="u">$</span>3</div><div className="k">Minimum to own a share</div></div>
              <div className="hstat"><div className="v tnum">100<span className="u">%</span></div><div className="k">Of prizes split to members</div></div>
            </div>
          </div>

          {/* Phone mockup — a preview of the live round in the app */}
          <div className="phone-stage">
            <div className="phone-glow" />
            <div className="phone">
              <div className="phone-screen">
                <div className="phone-island" />
                <div className="tg-bar">
                  <div className="x">✕</div>
                  <div className="t"><b>LottoChee</b><small>mini app</small></div>
                  <div className="x">⋯</div>
                </div>
                <div className="scr">
                  <div className="jk">
                    <div className="jk-top">
                      <span className="jk-live"><span className="dot live" />LIVE ROUND</span>
                      <span className="jk-id">LOTTO MAX · FRI</span>
                    </div>
                    <div className="jk-cap">Estimated jackpot</div>
                    <div className="jk-amt"><span className="cur">$</span><span className="big">70</span><span className="u">million CAD</span></div>
                    <div className="cd">
                      <div className="seg"><span>01</span><small>Days</small></div>
                      <span className="cl">:</span>
                      <div className="seg"><span>08</span><small>Hrs</small></div>
                      <span className="cl">:</span>
                      <div className="seg"><span>42</span><small>Min</small></div>
                      <span className="cl">:</span>
                      <div className="seg"><span>17</span><small>Sec</small></div>
                    </div>
                    <div className="poolrow">
                      <span className="muted">Pool · 12 shares</span>
                      <span className="mono"><span>$72</span><span> / $150</span></span>
                    </div>
                    <div className="bar"><span /></div>
                    <div className="players">
                      <div>
                        <div className="avstack">
                          {[0, 1, 2, 3].map(i => (
                            <div className="av" key={i}><svg viewBox="0 0 24 24" width="14" height="14" fill="rgba(255,255,255,.95)"><circle cx="12" cy="8.5" r="4" /><path d="M4 20c0-4.4 3.6-7.5 8-7.5s8 3.1 8 7.5z" /></svg></div>
                          ))}
                          <div className="av">+8</div>
                        </div>
                        <span className="cnt">12 players</span>
                      </div>
                      <span className="chip-gold chip">8.3% share</span>
                    </div>
                    <button className="jk-btn" onClick={go}>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14" /></svg>
                      Add shares · $6 each
                    </button>
                  </div>
                  <div className="ministat">
                    <div className="s"><div className="k">Your shares</div><div className="v">2 <span>/ 12</span></div></div>
                    <div className="s"><div className="k">Last win</div><div className="v win">+$38.40</div></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* ── PROOF BAND ── */}
      <div className="band">
        <div className="wrap band-in">
          <div className="band-item"><span className="v tnum">3</span><span className="l">national draws — Max, 6/49 &amp; Daily Grand</span></div>
          <div className="band-sep" />
          <div className="band-item"><span className="v tnum">$3</span><span className="l">minimum to own a share</span></div>
          <div className="band-sep" />
          <div className="band-item"><span className="v tnum">100%</span><span className="l">of prizes split back to members</span></div>
          <div className="band-sep" />
          <div className="band-item"><span className="v">≤ 2 min</span><span className="l">to join — Telegram or web</span></div>
        </div>
      </div>

      {/* ── HOW IT WORKS ── */}
      <section className="sec" id="how">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">How it works</span>
            <h2 className="h-sec">One pool, more tickets, a fair split.</h2>
            <p className="lede">No spreadsheets, no chasing friends for cash. Your group's trustee runs the pool end-to-end — you just buy a share and watch the draw.</p>
          </div>
          <div className="steps">
            <div className="step">
              <div className="step-n">1</div>
              <h3>Buy a share</h3>
              <p>Pick how many shares you want in the open round — $6 for Lotto&nbsp;Max, $3 for 6/49 and Daily&nbsp;Grand. Pay from your balance; top up by card or Interac e-Transfer.</p>
              <div className="step-meta"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="5" width="20" height="14" rx="3" /><path d="M2 10h20" /></svg>From $3</div>
            </div>
            <div className="step">
              <div className="step-n">2</div>
              <h3>The pool buys in</h3>
              <p>When the round fills, your trustee buys the official lottery tickets — Lotto&nbsp;Max, 6/49 or Daily&nbsp;Grand — on behalf of everyone in the group.</p>
              <div className="step-meta"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7h18l-1.5 10.5a2 2 0 0 1-2 1.5H6.5a2 2 0 0 1-2-1.5L3 7Z" /><path d="M8 7V5a4 4 0 0 1 8 0v2" /></svg>Official tickets</div>
            </div>
            <div className="step">
              <div className="step-n">3</div>
              <h3>Tickets go public</h3>
              <p>Every ticket is photographed and attached to the round before the draw. Anyone in the pool can open it and verify the numbers.</p>
              <div className="step-meta"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="6" width="18" height="14" rx="3" /><circle cx="12" cy="13" r="3.5" /><path d="M8 6l1.5-2h5L16 6" /></svg>Verifiable</div>
            </div>
            <div className="step">
              <div className="step-n">4</div>
              <h3>Winnings auto-split</h3>
              <p>Any prize is divided by your share and credited to your balance — and some wins even pay out free tickets for the next round.</p>
              <div className="step-meta"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v18" /><path d="M5 8h9a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h11" /></svg>By share</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── GROUPS ── */}
      <section className="sec" id="groups">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">Groups</span>
            <h2 className="h-sec">Play with your crew.<br />Or join theirs.</h2>
            <p className="lede">Run a private pool for your family, office or group chat — everyone buys shares together and splits whatever it wins. Or hop into an existing pool with a join code.</p>
          </div>
          <div className="groups-grid">
            <div className="group-card">
              <div className="group-card-head">
                <div className="group-ic create"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19a5.5 5.5 0 0 1 11 0" /><path d="M18 7v6M21 10h-6" /></svg></div>
                <div>
                  <h3>Start a group</h3>
                  <p>Request your own pool. Once a platform admin approves it, you become its trustee with a join code to share.</p>
                </div>
              </div>
              <label className="field">
                <span>Group name</span>
                <input className="ginput" type="text" defaultValue="Friday Office Pool" readOnly />
              </label>
              <div className="field">
                <span>Your invite code</span>
                <div className="code-row">
                  <code className="code mono">CREW-7F3K</code>
                  <button className="btn-mini" type="button" onClick={go}>Copy</button>
                </div>
              </div>
              <button className="btn btn-accent btn-block" type="button" onClick={go}>Request a group</button>
            </div>
            <div className="group-card">
              <div className="group-card-head">
                <div className="group-ic join"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" /><path d="M10 17l5-5-5-5" /><path d="M15 12H3" /></svg></div>
                <div>
                  <h3>Join with a code</h3>
                  <p>Got an invite? Drop the code to jump into the pool instantly.</p>
                </div>
              </div>
              <label className="field">
                <span>Group code</span>
                <input className="ginput mono" type="text" placeholder="e.g. CREW-29B7" onFocus={go} />
              </label>
              <button className="btn btn-tg btn-block" type="button" onClick={go}>Join group</button>
              <p className="join-hint">Codes look like <code className="mono">CREW-29B7</code>. Ask the group's host for theirs, or open their invite link.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── ODDS ── */}
      <section className="sec" id="odds">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">The math</span>
            <h2 className="h-sec">One ticket is one shot.<br />A pool is many.</h2>
            <p className="lede">For the price of a single line, a LottoChee share puts you across the whole pool. More lines in play means more chances to land a prize tier — you simply own your slice of whatever comes back.</p>
          </div>
          <div className="odds-grid">
            <div className="odds-card solo">
              <div className="tag">Going solo</div>
              <div className="big">1 line</div>
              <div className="sub">A few dollars buys you a single set of numbers.</div>
              <div className="lines"><span className="ln on" /></div>
              <div className="odds-foot">One ticket means <b>one</b> path to a prize — and a near-certain blank on most draws.</div>
            </div>
            <div className="odds-card pool">
              <div className="tag">A LottoChee pool</div>
              <div className="big">The pool</div>
              <div className="sub">The same share rides every ticket the pool holds.</div>
              <div className="lines">{Array.from({ length: 24 }).map((_, i) => <span className="ln" key={i} />)}</div>
              <div className="odds-foot"><b>Many more numbers</b> in the draw, and a far better shot at hitting a prize tier on any given draw night.</div>
            </div>
          </div>
          <div className="odds-note">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></svg>
            <span>Pooling raises the chance the group wins <em>something</em>, and any prize is shared in proportion to the shares you hold. It does not change the odds of any single ticket — Lotto&nbsp;Max jackpot odds are roughly 1 in 33.3 million per line.</span>
          </div>
        </div>
      </section>

      {/* ── TRANSPARENCY ── */}
      <section className="sec" id="trust">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">Transparency</span>
            <h2 className="h-sec">You can see every ticket.</h2>
            <p className="lede">Trust is the whole product. Before any draw, the proof is already in your hands.</p>
          </div>
          <div className="trans-grid">
            <div className="pillars">
              <div className="pillar">
                <div className="pic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="6" width="18" height="14" rx="3" /><circle cx="12" cy="13" r="3.5" /><path d="M8 6l1.5-2h5L16 6" /></svg></div>
                <div><h3>Photographed before the draw</h3><p>Every official ticket is scanned and attached to the round. The numbers are locked and public before a single ball drops.</p></div>
              </div>
              <div className="pillar">
                <div className="pic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3v18" /><path d="M5 8h9a3 3 0 0 1 0 6H8a3 3 0 0 0 0 6h11" /></svg></div>
                <div><h3>Splits computed by share</h3><p>Prizes divide by exactly the shares you hold, to the cent — the same formula for the $3 player and the $200 player.</p></div>
              </div>
              <div className="pillar">
                <div className="pic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 3v5h5" /><path d="M7 3h7l5 5v11a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" /><path d="M9 13h6M9 17h4" /></svg></div>
                <div><h3>A signed agreement, every round</h3><p>Every round comes with its own draw agreement — your shares, the pool and how the prize splits, in writing. Any participant can download it as a PDF.</p></div>
              </div>
              <div className="pillar">
                <div className="pic"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="10" width="16" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg></div>
                <div><h3>Funds held as your balance</h3><p>Credits and winnings sit in your own wallet. Top up by card or e-Transfer, and withdraw what you haven't staked anytime.</p></div>
              </div>
            </div>
            <div className="ticket-stage">
              <div className="ticket">
                <div className="tk-top"><b>LOTTO MAX</b><span>FRI · DRAW NIGHT</span></div>
                <div className="tk-label">Pool ticket · attached to the round</div>
                <div className="balls">
                  {[3, 11, 19, 24, 31, 38, 47].map(n => <span className="ball" key={n}>{String(n).padStart(2, '0')}</span>)}
                </div>
                <div className="tk-row"><span>Draw</span><span className="v">Fri 10:30 PM ET</span></div>
                <div className="tk-row"><span>Players on this round</span><span className="v">12</span></div>
                <div className="tk-row"><span>Your share</span><span className="v">8.3%</span></div>
                <div className="tk-stamp">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M20 6 9 17l-5-5" /></svg>
                  PHOTOGRAPHED &amp; POSTED
                </div>
              </div>
              <div className="ticket-badge"><span className="dot" />Photo on file</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── PLANS ── */}
      <section className="sec" id="plans">
        <div className="wrap">
          <div className="sec-head">
            <span className="eyebrow">Plans</span>
            <h2 className="h-sec">Two ways to run a group.</h2>
            <p className="lede">Every group picks one plan when it's created. Choose the model that fits how you play — it's set out in your group agreement.</p>
          </div>
          <div className="plans-grid">
            <div className="plan">
              <div className="plan-name">Monthly subscription</div>
              <div className="plan-price"><span className="amt">$6.99</span><span className="per">/ month</span></div>
              <div className="plan-sub">A simple flat fee for your group — and the platform takes no cut of any prize.</div>
              <ul className="plan-feats">
                <li><Check />Run unlimited rounds across Lotto&nbsp;Max, 6/49 &amp; Daily&nbsp;Grand</li>
                <li><Check />Keep 100% of every win — no share taken</li>
                <li><Check />Best for groups that play often</li>
              </ul>
            </div>
            <div className="plan feature">
              <span className="plan-badge">No monthly fee</span>
              <div className="plan-name">Big-prize share</div>
              <div className="plan-price"><span className="amt">5%</span><span className="per">of wins over $1,000</span></div>
              <div className="plan-sub">Nothing to pay up front — the platform only shares in a big win.</div>
              <ul className="plan-feats">
                <li><Check />$0 monthly — pay nothing until the group wins big</li>
                <li><Check />When a round wins more than $1,000, the platform may claim a 5% share</li>
                <li><Check />Spelled out in your group's signed agreement</li>
              </ul>
            </div>
          </div>
          <div className="plan-lock">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="10" width="16" height="11" rx="2.5" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
            <span>Your group chooses a plan once, when it's created. To keep things fair for every member, the choice is written into your group agreement and can't be changed later.</span>
          </div>
        </div>
      </section>

      {/* ── FAQ ── */}
      <section className="sec" id="faq">
        <div className="wrap">
          <div className="faq-grid">
            <div className="sec-head">
              <span className="eyebrow">Questions</span>
              <h2 className="h-sec">Good to know.</h2>
              <p className="lede">Everything members ask before their first round.</p>
            </div>
            <div className="faq-list">
              <details className="faq" open>
                <summary>How is this different from buying my own ticket?<span className="faq-plus" /></summary>
                <div className="ans">Instead of one line, your share rides every ticket the pool buys together. You get more numbers in play for the same money, and any prize is split in proportion to what you put in.</div>
              </details>
              <details className="faq">
                <summary>What happens if the pool wins?<span className="faq-plus" /></summary>
                <div className="ans">The prize is divided by share and credited straight to every member's balance once the trustee enters the official result. Some wins also award free tickets toward the next round.</div>
              </details>
              <details className="faq">
                <summary>How do I know the tickets are real?<span className="faq-plus" /></summary>
                <div className="ans">Every official lottery ticket is photographed and attached to the round before the draw, so the numbers are public and locked in advance. You can check them against the published draw yourself.</div>
              </details>
              <details className="faq">
                <summary>Is there an agreement for each round?<span className="faq-plus" /></summary>
                <div className="ans">Yes. Every round has its own draw agreement that sets out your shares, the pool and exactly how any prize is split. All participants can download it as a PDF from the round at any time.</div>
              </details>
              <details className="faq">
                <summary>What does a share cost?<span className="faq-plus" /></summary>
                <div className="ans">Shares are $6 for Lotto&nbsp;Max and $3 for Lotto&nbsp;6/49 and Daily&nbsp;Grand. Buy as many as you like in an open round, or set auto-participate to enter automatically each draw.</div>
              </details>
              <details className="faq">
                <summary>Can I withdraw my balance?<span className="faq-plus" /></summary>
                <div className="ans">Yes. Credits and winnings live in your wallet and can be withdrawn back to your card. There are no lock-ups on funds you haven't staked in a round.</div>
              </details>
              <details className="faq">
                <summary>Who can play?<span className="faq-plus" /></summary>
                <div className="ans">LottoChee is for players 19+ located in Canada. Please play within your means — set a budget and treat it as entertainment, not income. Support resources are linked below.</div>
              </details>
            </div>
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="wrap" id="cta">
        <div className="cta">
          <span className="eyebrow muted"><span className="dot live" />&nbsp;Join a pool before the next draw</span>
          <h2 className="display">Your next draw is waiting.<br /><span className="accentword">Pool in and play more lines.</span></h2>
          <p className="lede">Buy a share, join your group, and let the pool do the rest. Two minutes on Telegram or the web and you're in.</p>
          <div className="cta-row">
            <a className="btn btn-tg btn-lg" onClick={go}>Get started <Arrow s={18} /></a>
            <a className="btn btn-accent btn-lg" onClick={go}>Start a group</a>
          </div>
          <div className="channels center">
            <span className="channels-label">Two ways to play —</span>
            <span className="channel"><TgIcon />Telegram</span>
            <span className="channel"><WebIcon />Web app</span>
          </div>
          <div className="cta-fine">19+ · Canada · Play responsibly · Withdraw unspent credits anytime</div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="foot">
        <div className="wrap">
          <div className="foot-grid">
            <div>
              <a className="brand" href="#top" onClick={e => e.preventDefault()}>
                <LogoMark size={28} />
                <div className="brand-name">LottoChee</div>
              </a>
              <p>The group lottery syndicate for Lotto&nbsp;Max, 6/49 and Daily&nbsp;Grand — on Telegram or the web. Pool in, play more lines, split every prize.</p>
            </div>
            <div>
              <h4>Product</h4>
              <ul>
                <li><a href="#how">How it works</a></li>
                <li><a href="#odds">The odds</a></li>
                <li><a href="#plans">Plans</a></li>
                <li><a href="#trust">Transparency</a></li>
                <li><a onClick={go}>Open the app</a></li>
              </ul>
            </div>
            <div>
              <h4>Guides</h4>
              <ul>
                <li><a href="/canada-lottery-pool-guide/">Canada lottery pool guide</a></li>
                <li><a href="/how-lottery-pools-work/">How lottery pools work</a></li>
                <li><a href="/lotto-max-pool/">Lotto Max pools</a></li>
                <li><a href="/lotto-649-pool/">Lotto 6/49 pools</a></li>
                <li><a href="/daily-grand-pool/">Daily Grand pools</a></li>
              </ul>
            </div>
            <div>
              <h4>Responsible play</h4>
              <ul>
                <li><a href="/responsible-play/">Responsible play guide</a></li>
                <li><a href="#faq">Eligibility (19+ · Canada)</a></li>
                <li><a href="https://www.responsiblegambling.org" target="_blank" rel="noreferrer">Responsible Gambling Council</a></li>
                <li><a href="#trust">How prizes split</a></li>
              </ul>
            </div>
          </div>
          <div className="foot-base">
            <p>LottoChee organizes group ticket purchases on behalf of its members. It is an independent service and is not affiliated with, endorsed by, or operated by any official lottery operator. Estimated jackpot amounts are illustrative.</p>
            <div className="respo"><span className="age">19+</span> If gambling stops being fun, take a break — help is available across Canada through provincial responsible gambling resources.</div>
          </div>
        </div>
      </footer>

      {/* Sticky bottom action bar (mobile) */}
      <div className="mobile-bar">
        <div className="mb-meta">
          <div className="mb-amt"><span>3 draws</span> pooled</div>
          <div className="mb-sub"><span className="dot live" />Official tickets · split by share</div>
        </div>
        <a className="btn btn-tg" onClick={go}>Get started</a>
      </div>
    </div>
  )
}
