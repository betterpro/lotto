const BASE = import.meta.env.VITE_API_BASE ?? ''

function initData() {
  return window.Telegram?.WebApp?.initData ?? ''
}

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Init-Data': initData() },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  })
  if (!res.ok) {
    const text = await res.text()
    let msg = text
    try { msg = JSON.parse(text).detail ?? text } catch {}
    throw new Error(msg)
  }
  return res.json()
}

export const api = {
  me:           ()             => req('GET',  '/api/me'),
  invite:       ()             => req('GET',  '/api/invite'),
  settings:     {
    get: ()      => req('GET', '/api/settings'),
    put: (body)  => req('PUT', '/api/settings', body),
  },
  deposit:      (amount)       => req('POST', '/api/deposit', { amount }),
  etransfer: {
    info:    ()       => req('GET',  '/api/etransfer/info'),
    deposit: (amount) => req('POST', '/api/etransfer/deposit', { amount }),
  },
  round:        ()             => req('GET',  '/api/round'),
  rounds:       ()             => req('GET',  '/api/rounds'),
  participate:  (amount)       => req('POST', '/api/participate', { amount }),
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
    newRound:     (data)          => req('POST', '/api/admin/round/new', data),
    closeRound:   ()              => req('POST', '/api/admin/round/close'),
    draw:         ()              => req('POST', '/api/admin/round/draw'),  // legacy
    scanTicket:   (round_id, image_b64) => req('POST', '/api/admin/round/scan-ticket', { round_id, image_b64 }),
    uploadTicket: (round_id, numbers) => req('POST', '/api/admin/round/upload-ticket', { round_id, numbers }),
    results:      (round_id, winning_numbers, bonus_number, total_prize) =>
                                     req('POST', '/api/admin/round/results', { round_id, winning_numbers, bonus_number, total_prize }),
    round:        ()              => req('GET',  '/api/admin/round'),
    deposits:     ()              => req('GET',  '/api/admin/deposits'),
    resolve:      (id, action)    => req('POST', `/api/admin/deposits/${id}`, { action }),
    members:      ()              => req('GET',  '/api/admin/members'),
    checkEtransfer: ()            => req('POST', '/api/admin/etransfer/check'),
  },
}
