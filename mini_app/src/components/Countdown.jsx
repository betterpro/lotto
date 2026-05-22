import { useState, useEffect } from 'react'

export function Countdown({ to }) {
  const [diff, setDiff] = useState(0)

  useEffect(() => {
    const tick = () => setDiff(Math.max(0, new Date(to) - Date.now()))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [to])

  const totalSec = Math.floor(diff / 1000)
  const d = Math.floor(totalSec / 86400)
  const h = Math.floor((totalSec % 86400) / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60

  const pad = (n) => String(n).padStart(2, '0')

  if (totalSec <= 0) return (
    <div className="cd">
      <div className="cd-seg"><div className="n">00</div><div className="l">hrs</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">00</div><div className="l">min</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">00</div><div className="l">sec</div></div>
    </div>
  )

  if (d > 0) return (
    <div className="cd">
      <div className="cd-seg"><div className="n">{d}</div><div className="l">day{d !== 1 ? 's' : ''}</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">{pad(h)}</div><div className="l">hrs</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">{pad(m)}</div><div className="l">min</div></div>
    </div>
  )

  return (
    <div className="cd">
      <div className="cd-seg"><div className="n">{pad(h)}</div><div className="l">hrs</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">{pad(m)}</div><div className="l">min</div></div>
      <span className="cd-colon">:</span>
      <div className="cd-seg"><div className="n">{pad(s)}</div><div className="l">sec</div></div>
    </div>
  )
}
