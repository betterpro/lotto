import { LOGO_SRC } from '../brand.js'

/** The Lottochee token mark (blue→green lotto ball with a gold luck spark). */
export function LogoMark({ size = 48, style }) {
  return (
    <img src={LOGO_SRC} alt="" width={size} height={size}
      style={{ display: 'block', flexShrink: 0, ...style }} />
  )
}

/**
 * Full brand lockup: token mark + "Lottochee" wordmark.
 * `ink` renders the wordmark in navy for light backgrounds (default white).
 */
export default function Logo({ size = 48, wordmark = false, ink = false, gap, fontSize, style }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: gap ?? Math.round(size * 0.34), ...style }}>
      <LogoMark size={size} />
      {wordmark && (
        <span style={{
          fontFamily: '"Schibsted Grotesk", system-ui, -apple-system, sans-serif',
          fontWeight: 800, letterSpacing: '-.035em', lineHeight: 1,
          fontSize: fontSize ?? Math.round(size * 0.66),
          color: ink ? '#0b1118' : '#fff',
        }}>Lottochee</span>
      )}
    </div>
  )
}
