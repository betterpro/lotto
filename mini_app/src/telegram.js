// Telegram WebApp viewport & safe-area manager.
//
// Single source of truth for sizing the Mini App: SDK init, expanding out of the
// compact bottom-sheet, tracking the live viewport height, and resolving safe-area
// insets. Everything is published to CSS via custom properties on :root so the
// stylesheet can stay declarative.
//
// CSS variables exposed:
//   --sat / --sab / --sal / --sar          combined safe-area insets (px)
//   --tg-viewport-height                   live viewport height (px)
//   --tg-viewport-stable-height            stable viewport height, ex. keyboard (px)
//
// When not running inside Telegram these stay at their env()/100dvh fallbacks
// declared in index.css, so the app still sizes correctly on the open web.

const root = document.documentElement

function px(value) {
  return `${Math.max(0, Math.round(Number(value) || 0))}px`
}

function setVar(name, value) {
  root.style.setProperty(name, px(value))
}

// Device safe area (notch / dynamic island / home indicator) and Telegram's own
// content inset (the header carrying the close & menu buttons) stack on top of
// each other in fullscreen mode. Expose the *combined* inset so actionable
// content is never tucked under either one.
function applyInsets(tg) {
  const safe = tg.safeAreaInset || {}
  const content = tg.contentSafeAreaInset || {}
  setVar('--sat', (safe.top || 0) + (content.top || 0))
  setVar('--sab', (safe.bottom || 0) + (content.bottom || 0))
  setVar('--sal', (safe.left || 0) + (content.left || 0))
  setVar('--sar', (safe.right || 0) + (content.right || 0))
}

// viewportStableHeight is the right basis for the persistent app shell — it
// ignores transient chrome like the keyboard or a collapsing header — while
// viewportHeight tracks the live value for anything that should follow it.
function applyViewport(tg) {
  if (tg.viewportHeight) setVar('--tg-viewport-height', tg.viewportHeight)
  if (tg.viewportStableHeight) setVar('--tg-viewport-stable-height', tg.viewportStableHeight)
}

export function initTelegram() {
  const tg = window.Telegram?.WebApp
  if (!tg) return

  tg.ready?.()
  tg.expand?.()

  const apply = () => {
    applyInsets(tg)
    applyViewport(tg)
  }
  apply()
  // Insets/height are not always populated on the first synchronous read.
  requestAnimationFrame(apply)

  if (!tg.onEvent) return
  tg.onEvent('viewportChanged', apply)
  tg.onEvent('safeAreaChanged', apply)
  tg.onEvent('contentSafeAreaChanged', apply)
}
