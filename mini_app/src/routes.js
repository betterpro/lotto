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

// Full-screen sub-routes that aren't bottom-nav tabs. They map to an existing
// nav page so the tab bar stays highlighted and the route guard doesn't bounce
// them back home.
const SUBROUTE_PAGES = {
  '/topup': 'home',
}

/** Map URL pathname to bottom-nav page id. */
export function pathToPage(pathname) {
  return PATH_PAGES[pathname] ?? SUBROUTE_PAGES[pathname] ?? null
}

export const INVITE_SLUG_KEY = 'lottoo_pending_invite_slug'
const withoutInviteReferrer = value => value?.replace(/_r[0-9a-z]+$/i, '') || null

/** Resolve invite slug from Telegram start_param, URL path, or query. */
export function parseInviteSlug(pathname = '', search = '') {
  const sp = window.Telegram?.WebApp?.initDataUnsafe?.start_param
  if (sp) {
    if (sp.startsWith('join_')) return withoutInviteReferrer(sp.slice(5))
    if (sp.startsWith('g_')) return withoutInviteReferrer(sp.slice(2))
  }
  const joinMatch = pathname.match(/^\/join\/([^/]+)/)
  if (joinMatch) return withoutInviteReferrer(decodeURIComponent(joinMatch[1]))
  const params = new URLSearchParams(search)
  const q = params.get('join') || params.get('invite')
  if (q) return withoutInviteReferrer(q)
  return withoutInviteReferrer(localStorage.getItem(INVITE_SLUG_KEY))
}
