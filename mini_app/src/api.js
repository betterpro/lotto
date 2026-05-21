const BASE = import.meta.env.VITE_API_BASE ?? ''

function initData() {
  return window.Telegram?.WebApp?.initData ?? ''
}

async function req(method, path, body) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-Init-Data': initData() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? 'Request failed')
  return data
}

export const api = {
  me:           ()            => req('GET',  '/api/me'),
  deposit:      (amount)      => req('POST', '/api/deposit',    { amount }),
  round:        ()            => req('GET',  '/api/round'),
  participate:  (amount)      => req('POST', '/api/participate', { amount }),
  transactions: ()            => req('GET',  '/api/transactions'),
  admin: {
    newRound:  (drawDate)  => req('POST', '/api/admin/round/new',
                                  drawDate ? { draw_date: drawDate } : {}),
    closeRound:()          => req('POST', '/api/admin/round/close'),
    draw:      ()          => req('POST', '/api/admin/round/draw'),
    round:     ()          => req('GET',  '/api/admin/round'),
    deposits:  ()          => req('GET',  '/api/admin/deposits'),
    resolve: (id, action)  => req('POST', `/api/admin/deposits/${id}`, { action }),
    members:   ()          => req('GET',  '/api/admin/members'),
  },
}
