export default function Toast({ msg, error }) {
  return <div className={`toast${error ? ' error' : ''}`}>{msg}</div>
}
