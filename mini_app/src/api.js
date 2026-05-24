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
  const text = await res.text()
  if (!res.ok) {
    let msg = text
    try { msg = JSON.parse(text).detail ?? text } catch {}
    throw new Error(msg)
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error(
      'API returned HTML instead of JSON — is the backend running on port 8000?'
    )
  }
}

export const api = {
  me:           ()             => req('GET',  '/api/me'),
  invite:       ()             => req('GET',  '/api/invite'),
  agreement: {
    master: () => req('GET', '/api/agreement/master'),
    round:  (roundId) => req('GET', `/api/agreement/round/${roundId}`),
  },
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
    newRound:     (data)          => req('POST', '/api/admin/round/new', data),
    closeRound:   (round_id)      => req('POST', '/api/admin/round/close', { round_id }),
    draw:         ()              => req('POST', '/api/admin/round/draw'),  // legacy
    scanTicket:   (round_id, image_b64) => req('POST', '/api/admin/round/scan-ticket', { round_id, image_b64 }),
    uploadTicket: (round_id, numbers) => req('POST', '/api/admin/round/upload-ticket', { round_id, numbers }),
    results:      (round_id, winning_numbers, bonus_number, total_prize) =>
                                     req('POST', '/api/admin/round/results', { round_id, winning_numbers, bonus_number, total_prize }),
    round:        ()              => req('GET',  '/api/admin/round'),
    rounds:       ()              => req('GET',  '/api/admin/rounds'),
    deposits:     ()              => req('GET',  '/api/admin/deposits'),
    resolve:      (id, action)    => req('POST', `/api/admin/deposits/${id}`, { action }),
    members:      ()              => req('GET',  '/api/admin/members'),
    checkEtransfer: ()            => req('POST', '/api/admin/etransfer/check'),
  },
}
