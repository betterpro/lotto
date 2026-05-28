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
