/** Canadian national lottery games — keep in sync with lottery_types.py */

export const LOTTERY_TYPES = [
  { id: 'lotto_max',   name: 'Lotto Max',   shortName: 'Max', price: 6, logo: '/logos/lotto_max.png',   color: '#1e3a8a' },
  { id: '649',         name: 'Lotto 6/49',  shortName: '6/49', price: 3, logo: '/logos/649.png',         color: '#1d4ed8' },
  { id: 'daily_grand', name: 'Daily Grand', shortName: 'DG',   price: 3, logo: '/logos/DG.png', color: '#7c3aed' },
]

/** Profile auto-participate options (includes Max + 6/49 combo). */
export const LOTTERY_PREFS = [
  { v: 'lotto_max', label: 'Lotto Max', price: 6, tag: '$6/ticket' },
  { v: '649',       label: '6/49',      price: 3, tag: '$3/ticket' },
  { v: 'both',      label: 'Both',      price: 9, tag: '$9/combo' },
]

const _byId = Object.fromEntries(LOTTERY_TYPES.map(t => [t.id, t]))

export function lotteryMeta(type) {
  if (type && _byId[type]) return _byId[type]
  const label = (type || 'unknown').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return { id: type, name: label, shortName: label.slice(0, 4), price: 3, color: '#64748b' }
}

export function lotterySharePrice(type) {
  return lotteryMeta(type).price
}

/** Ticket row layout per game — keep in sync with lottery_types.py */
export const TICKET_LAYOUTS = {
  lotto_max: {
    rows: [
      { label: 'Line 1', count: 7, min: 1, max: 52 },
      { label: 'Line 2', count: 7, min: 1, max: 52 },
      { label: 'Line 3', count: 7, min: 1, max: 52 },
    ],
  },
  '649': {
    rows: [{ label: '6/49 numbers', count: 6, min: 1, max: 49 }],
  },
  daily_grand: {
    rows: [
      { label: 'Main numbers', count: 5, min: 1, max: 49 },
      { label: 'Grand number', count: 1, min: 1, max: 7 },
    ],
  },
}

export function ticketLayout(type) {
  return TICKET_LAYOUTS[type] || TICKET_LAYOUTS.lotto_max
}

export function emptyTicketRows(layout) {
  return layout.rows.map(r => Array(r.count).fill(''))
}

/** @returns {string[][]} */
export function parseTicketNumbers(raw) {
  if (!raw) return []
  let data
  try { data = typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return [] }
  if (!Array.isArray(data) || !data.length) return []
  if (typeof data[0] === 'number') return [data.map(String)]
  return data.map(row => (Array.isArray(row) ? row : []).map(String))
}

export function ticketRowsValid(rows, layout) {
  return layout.rows.every((spec, i) => {
    const row = rows[i] || []
    if (row.length !== spec.count) return false
    return row.every(n => {
      const v = Number(n)
      return Number.isInteger(v) && v >= spec.min && v <= spec.max
    })
  })
}

export function ticketRowsToNumbers(rows) {
  return rows.map(row => row.map(n => Number(n)))
}

export function mergeScannedRows(scanned, layout) {
  const base = emptyTicketRows(layout)
  if (!scanned?.length) return base
  return layout.rows.map((spec, i) => {
    const src = scanned[i] || []
    return Array.from({ length: spec.count }, (_, j) => {
      const v = src[j]
      return v != null && v !== '' ? String(v) : (base[i][j] || '')
    })
  })
}
