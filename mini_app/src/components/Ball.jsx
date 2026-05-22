export function Ball({ n, match, bonus, size = 'md' }) {
  const cls = `ball ${size} ${bonus ? 'bonus' : match ? 'match' : 'def'}`
  return <span className={cls}>{n}</span>
}
