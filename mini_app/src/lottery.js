export const LOTTERY_TYPES = [
  { id: 'lotto_max', name: 'Lotto Max', price: 6, logo: '/max.png' },
  { id: '649',       name: '6/49',      price: 3, logo: '/649.png' },
]

export function lotteryMeta(type) {
  return LOTTERY_TYPES.find(t => t.id === type) || LOTTERY_TYPES[0]
}
