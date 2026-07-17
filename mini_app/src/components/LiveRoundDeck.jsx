import { useState, useRef } from 'react'
import { lotteryMeta } from '../lottery.js'
import LotteryLogo from './LotteryLogo.jsx'

const SWIPE_THRESHOLD = 48

function shortDate(s) {
  if (!s) return 'Draw TBD'
  const d = new Date(s.includes('T') ? s : s + 'T00:00:00')
  return isNaN(d.getTime()) ? s : d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' })
}

export default function LiveRoundDeck({ rounds, index, onIndexChange, renderCard }) {
  const [dragX, setDragX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)
  const startY = useRef(0)
  const horizontal = useRef(false)

  if (!rounds?.length) return null

  const multi = rounds.length > 1
  if (!multi) {
    return <div className="live-round-deck">{renderCard(rounds[0])}</div>
  }

  const go = (i) => onIndexChange(Math.max(0, Math.min(rounds.length - 1, i)))

  function pointerX(e) { return e.clientX ?? e.touches?.[0]?.clientX ?? 0 }
  function pointerY(e) { return e.clientY ?? e.touches?.[0]?.clientY ?? 0 }

  function onStart(e) {
    setIsDragging(true)
    horizontal.current = false
    startX.current = pointerX(e)
    startY.current = pointerY(e)
  }
  function onMove(e) {
    if (!isDragging) return
    const dx = pointerX(e) - startX.current
    const dy = pointerY(e) - startY.current
    // Lock to horizontal only once the gesture is clearly sideways (lets the
    // page scroll vertically otherwise).
    if (!horizontal.current && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy)) {
      horizontal.current = true
    }
    if (horizontal.current) setDragX(dx)
  }
  function onEnd() {
    if (!isDragging) return
    setIsDragging(false)
    if (dragX > SWIPE_THRESHOLD) go(index - 1)
    else if (dragX < -SWIPE_THRESHOLD) go(index + 1)
    setDragX(0)
    horizontal.current = false
  }

  const arrowBtn = (dir) => ({
    position: 'absolute', top: '42%', [dir]: 2, zIndex: 3,
    width: 34, height: 34, borderRadius: '50%', border: 'none', cursor: 'pointer',
    background: 'rgba(15,22,30,.72)', color: '#fff', fontSize: 20, lineHeight: '34px',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    boxShadow: '0 2px 8px rgba(0,0,0,.3)', backdropFilter: 'blur(2px)',
  })

  return (
    <div className="live-round-deck">
      {/* Round selector tabs — makes it obvious there are several rounds */}
      <div style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '0 0 12px', scrollbarWidth: 'none' }}>
        {rounds.map((r, i) => {
          const meta = lotteryMeta(r.lottery_type)
          const on = i === index
          return (
            <button key={r.id} type="button" onClick={() => go(i)}
              style={{
                flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 12px 7px 8px', borderRadius: 12, cursor: 'pointer',
                border: `1px solid ${on ? 'var(--tg)' : 'var(--hairline-2)'}`,
                background: on ? 'rgba(46,166,255,.14)' : 'var(--bg-3)',
              }}>
              <LotteryLogo type={r.lottery_type} height={22} style={{ width: 30, flexShrink: 0 }} />
              <div className="col" style={{ alignItems: 'flex-start', gap: 1 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: on ? 'var(--tg)' : 'var(--tx-1)', lineHeight: 1.1 }}>
                  {meta.shortName}
                </span>
                <span style={{ fontSize: 10.5, color: 'var(--tx-3)', lineHeight: 1.1 }}>
                  {shortDate(r.draw_date)}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {/* Card with side arrows + horizontal swipe */}
      <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 20 }}>
        {index > 0 && (
          <button type="button" aria-label="Previous round" onClick={() => go(index - 1)} style={arrowBtn('left')}>‹</button>
        )}
        {index < rounds.length - 1 && (
          <button type="button" aria-label="Next round" onClick={() => go(index + 1)} style={arrowBtn('right')}>›</button>
        )}
        <div
          style={{
            display: 'flex',
            transform: `translateX(calc(${-index * 100}% + ${dragX}px))`,
            transition: isDragging ? 'none' : 'transform .3s cubic-bezier(.4,0,.2,1)',
            touchAction: 'pan-y',
          }}
          onPointerDown={onStart}
          onPointerMove={onMove}
          onPointerUp={onEnd}
          onPointerCancel={onEnd}
        >
          {rounds.map((r, i) => (
            <div key={r.id} style={{ flex: '0 0 100%', minWidth: 0 }}>
              {renderCard(r, i !== index)}
            </div>
          ))}
        </div>
      </div>

      {/* Dots + counter */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 6, marginTop: 12 }}>
        {rounds.map((r, i) => (
          <button key={r.id} type="button" onClick={() => go(i)} aria-label={`Round ${i + 1}`}
            style={{
              width: i === index ? 20 : 7, height: 7, borderRadius: 99, border: 'none', padding: 0,
              background: i === index ? 'var(--tg)' : 'var(--hairline-2)',
              cursor: 'pointer', transition: 'width .2s, background .2s',
            }} />
        ))}
      </div>
      <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--tx-3)', marginTop: 6 }}>
        Round {index + 1} of {rounds.length} · tap a game or swipe
      </div>
    </div>
  )
}
