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
  deposit:      (amount)       => req('POST', '/api/deposit', { amount }),
  round:        ()             => req('GET',  '/api/round'),
  participate:  (amount)       => req('POST', '/api/participate', { amount }),
  transactions: ()             => req('GET',  '/api/transactions'),
  stripe: {
    config:             ()       => req('GET',  '/api/stripe/config'),
    createPaymentIntent:(amount) => req('POST', '/api/stripe/payment-intent', { amount }),
    createSubscription: (amount) => req('POST', '/api/stripe/subscription/create', { amount }),
    subscription:       ()       => req('GET',  '/api/stripe/subscription'),
    updateSub:          (amount) => req('POST', '/api/stripe/subscription/update', { amount }),
    cancelSub:          ()       => req('POST', '/api/stripe/subscription/cancel'),
  },
  admin: {
    newRound:  (drawDate) => req('POST', '/api/admin/round/new', drawDate ? { draw_date: drawDate } : {}),
    closeRound:()         => req('POST', '/api/admin/round/close'),
    draw:      ()         => req('POST', '/api/admin/round/draw'),
    round:     ()         => req('GET',  '/api/admin/round'),
    deposits:  ()         => req('GET',  '/api/admin/deposits'),
    resolve:   (id, action) => req('POST', `/api/admin/deposits/${id}`, { action }),
    members:   ()         => req('GET',  '/api/admin/members'),
  },
}
