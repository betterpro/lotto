import { lotteryMeta } from '../lottery.js'

export default function LotteryLogo({ type, height = 40, style, className }) {
  const meta = lotteryMeta(type)
  if (meta.logo) {
    return (
      <img
        src={meta.logo}
        alt={meta.name}
        className={className}
        style={{ height, width: '100%', objectFit: 'contain', ...style }}
      />
    )
  }
  return (
    <div
      className={className}
      title={meta.name}
      style={{
        height,
        minWidth: height * 1.4,
        borderRadius: 8,
        background: `${meta.color}22`,
        border: `.5px solid ${meta.color}55`,
        color: meta.color,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontWeight: 800,
        fontSize: Math.max(10, height * 0.28),
        letterSpacing: '.2px',
        fontFamily: 'var(--mono)',
        ...style,
      }}
    >
      {meta.shortName || meta.name.slice(0, 4)}
    </div>
  )
}
