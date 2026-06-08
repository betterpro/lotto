function setInsetVar(name, value) {
  document.documentElement.style.setProperty(name, `${Math.max(0, Number(value) || 0)}px`)
}

function applyTelegramInsets() {
  const tg = window.Telegram?.WebApp
  if (!tg) return

  const inset = tg.contentSafeAreaInset ?? tg.safeAreaInset
  if (!inset) return

  setInsetVar('--sat', inset.top)
  setInsetVar('--sab', inset.bottom)
  setInsetVar('--sal', inset.left)
  setInsetVar('--sar', inset.right)
}

export function initSafeArea() {
  applyTelegramInsets()

  const tg = window.Telegram?.WebApp
  if (!tg) return

  tg.ready?.()
  applyTelegramInsets()
  requestAnimationFrame(applyTelegramInsets)

  if (!tg.onEvent) return

  const refresh = () => applyTelegramInsets()
  tg.onEvent('contentSafeAreaChanged', refresh)
  tg.onEvent('safeAreaChanged', refresh)
  tg.onEvent('viewportChanged', refresh)
}
