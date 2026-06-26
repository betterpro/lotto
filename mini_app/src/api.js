import { isTelegram } from './routes.js'

const BASE = import.meta.env.VITE_API_BASE ?? ''
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS ?? 20000)

export function authHeaders(extra = {}) {
  const headers = { ...extra }
  const id = window.Telegram?.WebApp?.initData
  if (id) headers['X-Init-Data'] = id
  return headers
}

/** Authenticated fetch — session cookie on web, initData in Telegram. */
export function authFetch(path, options = {}) {
  const { headers: optHeaders, ...rest } = options
  return fetch(BASE + path, {
    credentials: 'include',
    ...rest,
    headers: authHeaders(optHeaders ?? {}),
  })
}

async function req(method, path, body) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  let res
  try {
    res = await authFetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('API request timed out. Please reopen the app or try again.')
    }
    throw error
  } finally {
    window.clearTimeout(timeout)
  }

  const text = await res.text()
  if (!res.ok) {
    let msg = text
    try {
      const j = JSON.parse(text)
      const d = j.detail
      msg = Array.isArray(d) ? d.map(x => x.msg || String(x)).join('; ') : (d ?? text)
    } catch {}
    throw new Error(typeof msg === 'string' ? msg : 'API request failed')
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(
      'API returned HTML instead of JSON — is the backend running on port 8000?'
    )
  }
}

async function reqPublic(method, path) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  let res
  try {
    res = await fetch(BASE + path, { method, signal: controller.signal })
  } finally {
    window.clearTimeout(timeout)
  }
  const text = await res.text()
  if (!res.ok) {
    let msg = text
    try { msg = JSON.parse(text).detail ?? text } catch {}
    throw new Error(msg || 'Request failed')
  }
  return JSON.parse(text)
}

export const api = {
  auth: {
    config:        () => reqPublic('GET', '/api/auth/config'),
    telegramLogin: (data) => req('POST', '/api/auth/telegram', data),
    signup:        (data) => req('POST', '/api/auth/signup', data),
    login:         (data) => req('POST', '/api/auth/login', data),
    google:        (data) => req('POST', '/api/auth/google', data),
    logout:        () => req('POST', '/api/auth/logout'),
  },
  me:           ()             => req('GET',  '/api/me'),
  invite:       (groupId) => req('GET', groupId ? `/api/invite?group_id=${groupId}` : '/api/invite'),
  groups: {
    list:      () => req('GET', '/api/groups'),
    setActive: (group_id) => req('POST', '/api/groups/active', { group_id }),
  },
  group: {
    preview: (slug) => reqPublic('GET', `/api/group/preview?slug=${encodeURIComponent(slug)}`),
    join:    (slug) => req('POST', '/api/group/join', { slug }),
    joinByCode: (code) => req('POST', '/api/group/join-code', { code }),
  },
  trustee: {
    application: () => req('GET', '/api/trustee/application'),
    apply:       (proposed_group_name, pricing_plan) => req('POST', '/api/trustee/apply', { proposed_group_name, pricing_plan }),
  },
  platform: {
    overview:      () => req('GET', '/api/platform/overview'),
    groups:        () => req('GET', '/api/platform/groups'),
    group:         (id) => req('GET', `/api/platform/groups/${id}`),
    users:         (params = {}) => {
      const q = new URLSearchParams()
      if (params.group_id != null) q.set('group_id', params.group_id)
      if (params.limit) q.set('limit', params.limit)
      const s = q.toString()
      return req('GET', `/api/platform/users${s ? `?${s}` : ''}`)
    },
    patchUser:     (telegramId, body) => req('PATCH', `/api/platform/users/${telegramId}`, body),
    rounds:        (params = {}) => {
      const q = new URLSearchParams()
      if (params.group_id) q.set('group_id', params.group_id)
      if (params.status) q.set('status', params.status)
      const s = q.toString()
      return req('GET', `/api/platform/rounds${s ? `?${s}` : ''}`)
    },
    applications:  () => req('GET', '/api/platform/applications'),
    approveApp:    (id) => req('POST', `/api/platform/applications/${id}/approve`),
    rejectApp:     (id, review_notes) => req('POST', `/api/platform/applications/${id}/reject`, { review_notes }),
    patchGroup:    (id, body) => req('PATCH', `/api/platform/groups/${id}`, body),
  },
  agreement: {
    master: () => req('GET', '/api/agreement/master'),
    round:  (roundId) => req('GET', `/api/agreement/round/${roundId}`),
    downloadToken: () => req('GET', '/api/agreement/download-token'),
  },
  beneficiary: {
    save: (data) => req('POST', '/api/beneficiary', data),
  },
  profile: {
    updateEmail: (email) => req('PATCH', '/api/profile/email', { email }),
  },
  settings:     {
    get: ()      => req('GET', '/api/settings'),
    put: (body)  => req('PUT', '/api/settings', body),
  },
  deposit:      (amount)       => req('POST', '/api/deposit', { amount }),
  payment: {
    options: () => req('GET', '/api/payment/options'),
  },
  etransfer: {
    info:    ()       => req('GET',  '/api/etransfer/info'),
    deposit: (amount) => req('POST', '/api/etransfer/deposit', { amount }),
  },
  round:        ()             => req('GET',  '/api/round'),
  rounds: {
    list: ()     => req('GET',  '/api/rounds'),
    open: ()     => req('GET',  '/api/rounds/open'),
  },
  participate:  (amount, round_id) => req('POST', '/api/participate', { amount, round_id }),
  transactions: ()             => req('GET',  '/api/transactions'),
  stripe: {
    config:              ()       => req('GET',  '/api/stripe/config'),
    createPaymentIntent: (amount) => req('POST', '/api/stripe/payment-intent', { amount }),
    createSubscription:  (amount) => req('POST', '/api/stripe/subscription/create', { amount }),
    subscription:        ()       => req('GET',  '/api/stripe/subscription'),
    updateSub:           (amount) => req('POST', '/api/stripe/subscription/update', { amount }),
    cancelSub:           ()       => req('POST', '/api/stripe/subscription/cancel'),
  },
  admin: {
    suggestRound: (lottery_type, draw_date) => {
      const q = new URLSearchParams({ lottery_type })
      if (draw_date) q.set('draw_date', draw_date)
      return req('GET', `/api/admin/round/suggest?${q}`)
    },
    newRound:     (data)          => req('POST', '/api/admin/round/new', data),
    setJackpot:   (round_id, opts) => req('POST', '/api/admin/round/jackpot',
      opts?.fetch ? { round_id, fetch: true } : { round_id, jackpot: opts.jackpot }),
    closeRound:   (round_id)      => req('POST', '/api/admin/round/close', { round_id }),
    deleteRound:  (round_id)      => req('POST', '/api/admin/round/delete', { round_id }),
    draw:         ()              => req('POST', '/api/admin/round/draw'),  // legacy
    scanTicket:   (round_id, image_b64, opts = {}) => req('POST', '/api/admin/round/scan-ticket', {
      round_id, image_b64, ticket_index: opts.ticket_index, rows: opts.rows,
      draw_date: opts.draw_date, preview: opts.preview,
    }),
    saveTicket:   (round_id, ticket_index, rows, image_b64, draw_date) =>
      req('POST', '/api/admin/round/ticket', { round_id, ticket_index, rows, image_b64, draw_date }),
    uploadTicket: (round_id, numbers) => req('POST', '/api/admin/round/upload-ticket',
      numbers != null ? { round_id, numbers } : { round_id }),
    results:      (round_id, winning_numbers, bonus_number, total_prize, free_tickets) =>
                                     req('POST', '/api/admin/round/results', {
                                       round_id, winning_numbers, bonus_number, total_prize, free_tickets,
                                     }),
    round:        ()              => req('GET',  '/api/admin/round'),
    rounds:       ()              => req('GET',  '/api/admin/rounds'),
    deposits:     ()              => req('GET',  '/api/admin/deposits'),
    resolve:      (id, action)    => req('POST', `/api/admin/deposits/${id}`, { action }),
    members:      ()              => req('GET',  '/api/admin/members'),
    checkEtransfer: ()            => req('POST', '/api/admin/etransfer/check'),
    group: {
      get:   () => req('GET', '/api/admin/group'),
      patch: (body) => req('PATCH', '/api/admin/group', body),
      stripeStatus:  () => req('GET',  '/api/admin/group/stripe/status'),
      stripeConnect: () => req('POST', '/api/admin/group/stripe/connect'),
      subscription:       () => req('GET',  '/api/admin/group/subscription'),
      subscriptionCreate: () => req('POST', '/api/admin/group/subscription/create'),
      subscriptionCancel: () => req('POST', '/api/admin/group/subscription/cancel'),
    },
  },
}

export { isTelegram, BASE }
