import { createContext, useContext, useState, useCallback, useRef } from 'react'

const ToastContext = createContext(null)

const ICONS = {
  success: '✓',
  error: '✕',
  warn: '!',
  info: 'i',
}

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null)
  const timerRef = useRef(null)

  const showToast = useCallback((msg, type = 'info') => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setToast({ msg, type })
    timerRef.current = setTimeout(() => {
      setToast(null)
      timerRef.current = null
    }, 3600)
  }, [])

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      {toast && (
        <div className="toast-host" role="status" aria-live="polite">
          <div className={`toast toast-${toast.type}`}>
            <span className="toast-icon" aria-hidden="true">{ICONS[toast.type] ?? ICONS.info}</span>
            <span className="toast-msg">{toast.msg}</span>
          </div>
        </div>
      )}
    </ToastContext.Provider>
  )
}

export function useToast() {
  const showToast = useContext(ToastContext)
  if (!showToast) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return showToast
}
