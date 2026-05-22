import { useState, useCallback } from 'react'

export function useToast() {
  const [toast, setToast] = useState(null)

  const showToast = useCallback((msg, type = 'default') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3200)
  }, [])

  const node = toast ? (
    <div className={`toast${toast.type === 'error' ? ' error' : toast.type === 'success' ? ' success' : ''}`}>
      {toast.msg}
    </div>
  ) : null

  return [showToast, node]
}

export default function Toast({ msg, error }) {
  return <div className={`toast${error ? ' error' : ''}`}>{msg}</div>
}
