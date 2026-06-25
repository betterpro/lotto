import { useState, useRef } from 'react'

const SWIPE_THRESHOLD = 56

export default function LiveRoundDeck({ rounds, index, onIndexChange, renderCard }) {
  const [dragX, setDragX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const startX = useRef(0)

  if (!rounds?.length) return null

  function pointerX(e) {
    return e.clientX ?? e.touches?.[0]?.clientX ?? 0
  }

  function onStart(e) {
    setIsDragging(true)
    startX.current = pointerX(e)
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }

  function onMove(e) {
    if (!isDragging) return
    setDragX(pointerX(e) - startX.current)
  }

  function onEnd() {
    if (!isDragging) return
    setIsDragging(false)
    if (dragX > SWIPE_THRESHOLD && index > 0) onIndexChange(index - 1)
    else if (dragX < -SWIPE_THRESHOLD && index < rounds.length - 1) onIndexChange(index + 1)
    setDragX(0)
  }

  if (rounds.length === 1) {
    return (
      <div style={{ padding: '8px 16px 4px' }}>
        {renderCard(rounds[0])}
      </div>
    )
  }

  const next = index < rounds.length - 1 ? rounds[index + 1] : null
  const prev = index > 0 ? rounds[index - 1] : null
  const peek = dragX < 0 ? next : dragX > 0 ? prev : next

  return (
    <div style={{ padding: '8px 16px 4px', userSelect: 'none', touchAction: 'pan-y' }}>
      <div style={{ position: 'relative', minHeight: 320 }}>
        {peek && (
          <div style={{
            position: 'absolute', inset: '10px 14px 0', zIndex: 0,
            transform: 'scale(0.94) translateY(8px)', opacity: 0.45,
            pointerEvents: 'none', filter: 'brightness(0.85)',
          }}>
            {renderCard(peek, true)}
          </div>
        )}
        <div
          style={{
            position: 'relative', zIndex: 1,
            transform: `translateX(${dragX}px) rotate(${dragX * 0.04}deg)`,
            transition: isDragging ? 'none' : 'transform 0.28s cubic-bezier(.4,0,.2,1)',
            cursor: 'grab',
          }}
          onPointerDown={onStart}
          onPointerMove={onMove}
          onPointerUp={onEnd}
          onPointerCancel={onEnd}
        >
          {renderCard(rounds[index])}
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: 6, marginTop: 10 }}>
        {rounds.map((r, i) => (
          <button key={r.id} onClick={() => onIndexChange(i)} aria-label={`Round ${r.id}`}
            style={{
              width: i === index ? 18 : 6, height: 6, borderRadius: 99, border: 'none', padding: 0,
              background: i === index ? 'var(--tg)' : 'var(--hairline-2)',
              cursor: 'pointer', transition: 'width .2s, background .2s',
            }} />
        ))}
      </div>
      <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--tx-3)', marginTop: 6 }}>
        Swipe for more · {index + 1} of {rounds.length}
      </div>
    </div>
  )
}
