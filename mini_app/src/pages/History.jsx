import { useState, useEffect } from 'react'
import { api } from '../api.js'

const ICON = { deposit: '💰', withdraw: '💸', participate: '🎟', win: '🏆', refund: '↩️' }
const SIGN = { deposit: '+', withdraw: '-', participate: '-', win: '+', refund: '+' }

export default function History() {
  const [txs, setTxs] = useState(null)
  useEffect(() => { api.transactions().then(d => setTxs(d.transactions)).catch(() => setTxs([])) }, [])

  if (!txs) return (
    <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: 80 }}>
      <div className="spinner" />
    </div>
  )

  if (txs.length === 0) return (
    <div className="page">
      <div className="empty-state">
        <div className="icon">📋</div>
        <p>No transactions yet</p>
        <p className="hint">Your activity will appear here.</p>
      </div>
    </div>
  )

  return (
    <div className="page">
      <div className="section-label">Transaction History</div>
      <div className="card">
        {txs.map(tx => {
          const pos = SIGN[tx.type] === '+'
          return (
            <div key={tx.id} className="list-row">
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: 26 }}>{ICON[tx.type] ?? '•'}</span>
                <div>
                  <div style={{ fontWeight: 500, textTransform: 'capitalize' }}>{tx.type}</div>
                  {tx.note && <div className="hint" style={{ fontSize: 12 }}>{tx.note}</div>}
                  <div className="hint" style={{ fontSize: 11 }}>
                    {tx.created_at.slice(0, 16).replace('T', ' ')}
                  </div>
                </div>
              </div>
              <div className={pos ? 'pos' : 'neg'} style={{ fontSize: 16 }}>
                {SIGN[tx.type]}{tx.amount.toFixed(2)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
