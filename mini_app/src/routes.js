/** True when running inside Telegram with valid initData. */
export function isTelegram() {
  return !!window.Telegram?.WebApp?.initData
}

export const PAGE_PATHS = {
  home: '/',
  rounds: '/rounds',
  history: '/activity',
  profile: '/profile',
  admin: '/admin',
  platform: '/platform',
}

const PATH_PAGES = Object.fromEntries(
  Object.entries(PAGE_PATHS).map(([page, path]) => [path, page]),
)

/** Map URL pathname to bottom-nav page id. */
export function pathToPage(pathname) {
  return PATH_PAGES[pathname] ?? null
}

export const INVITE_SLUG_KEY = 'lottoo_pending_invite_slug'

/** Resolve invite slug from Telegram start_param, URL path, or query. */
export function parseInviteSlug(pathname = '', search = '') {
  const sp = window.Telegram?.WebApp?.initDataUnsafe?.start_param
  if (sp) {
    if (sp.startsWith('join_')) return sp.slice(5)
    if (sp.startsWith('g_')) return sp.slice(2)
  }
  const joinMatch = pathname.match(/^\/join\/([^/]+)/)
  if (joinMatch) return decodeURIComponent(joinMatch[1])
  const params = new URLSearchParams(search)
  const q = params.get('join') || params.get('invite')
  if (q) return q
  return localStorage.getItem(INVITE_SLUG_KEY) || null
}
