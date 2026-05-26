import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'

const TABS = ['overview', 'applications', 'groups', 'users', 'rounds']

export default function PlatformAdmin() {
  const showToast = useToast()
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [applications, setApplications] = useState([])
  const [groups, setGroups] = useState([])
  const [users, setUsers] = useState([])
  const [rounds, setRounds] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (tab === 'overview') setOverview(await api.platform.overview())
      if (tab === 'applications') {
        const r = await api.platform.applications()
        setApplications(r.applications || [])
      }
      if (tab === 'groups') {
        const r = await api.platform.groups()
        setGroups(r.groups || [])
      }
      if (tab === 'users') {
        const r = await api.platform.users()
        setUsers(r.users || [])
      }
      if (tab === 'rounds') {
        const r = await api.platform.rounds()
        setRounds(r.rounds || [])
      }
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [tab, showToast])

  useEffect(() => { load() }, [load])

  async function approve(id) {
    try {
      await api.platform.approveApp(id)
      showToast('Group created', 'success')
      load()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  async function reject(id) {
    try {
      await api.platform.rejectApp(id, 'Not approved at this time')
      showToast('Application rejected', 'success')
      load()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  return (
    <div className="tab-content">
      <div style={{ padding: '12px 16px 8px' }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 4px' }}>Platform admin</h2>
        <p style={{ fontSize: 12, color: 'var(--tx-2)', margin: 0 }}>Manage all groups and users</p>
      </div>

      <div style={{ padding: '0 16px 12px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button
            key={t}
            className={'chip' + (tab === t ? ' chip-gold' : '')}
            onClick={() => setTab(t)}
            style={{ textTransform: 'capitalize' }}
          >
            {t}
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ padding: 40, display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
      ) : tab === 'overview' && overview ? (
        <div style={{ padding: '0 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {Object.entries(overview).map(([k, v]) => (
            <div key={k} className="stat">
              <span className="k">{k.replace(/_/g, ' ')}</span>
              <span className="v">{v}</span>
            </div>
          ))}
        </div>
      ) : tab === 'applications' ? (
        <div className="stack">
          {applications.length === 0 ? (
            <p style={{ padding: 16, color: 'var(--tx-2)', fontSize: 13 }}>No pending applications.</p>
          ) : applications.map(a => (
            <div key={a.id} className="card" style={{ padding: 14 }}>
              <div style={{ fontWeight: 600 }}>{a.proposed_group_name}</div>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 4 }}>
                {a.full_name || a.username} · #{a.applicant_user_id}
              </div>
              <div className="row gap-8" style={{ marginTop: 12 }}>
                <button className="btn btn-primary btn-sm" onClick={() => approve(a.id)}>Approve</button>
                <button className="btn btn-ghost btn-sm" onClick={() => reject(a.id)}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      ) : tab === 'groups' ? (
        <div className="stack">
          {groups.map(g => (
            <div key={g.id} className="card" style={{ padding: 14 }}>
              <div className="row between">
                <span style={{ fontWeight: 600 }}>{g.name}</span>
                <span className="chip" style={{ fontSize: 10 }}>{g.status}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 4 }}>
                Trustee: {g.trustee_name || g.trustee_username} · {g.member_count} members · {g.slug}
              </div>
            </div>
          ))}
        </div>
      ) : tab === 'users' ? (
        <div className="stack">
          {users.slice(0, 100).map(u => (
            <div key={u.telegram_id} className="card" style={{ padding: 12 }}>
              <div style={{ fontWeight: 500 }}>{u.full_name || u.username}</div>
              <div style={{ fontSize: 11, color: 'var(--tx-3)' }}>
                {u.group_name || 'No group'} · ${Number(u.credit || 0).toFixed(2)}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="stack">
          {rounds.map(r => (
            <div key={r.id} className="card" style={{ padding: 12 }}>
              <div style={{ fontWeight: 600 }}>Round #{r.id} · {r.group_name}</div>
              <div style={{ fontSize: 11, color: 'var(--tx-3)' }}>
                {r.status} · pool ${Number(r.pool || 0).toFixed(2)} · {r.participants_count} players
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
