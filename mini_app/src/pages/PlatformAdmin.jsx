import { useState, useEffect, useCallback } from 'react'
import { api } from '../api.js'
import { useToast } from '../components/Toast.jsx'
import { Sheet } from '../components/Sheet.jsx'
import TelegramAvatar from '../components/TelegramAvatar.jsx'

const TABS = ['overview', 'applications', 'groups', 'users', 'rounds']

function fmtCAD(n) {
  return '$' + Number(n || 0).toFixed(2)
}

function StatusChip({ status }) {
  const active = status === 'active'
  return (
    <span className={'chip' + (active ? '' : '')} style={{
      fontSize: 10,
      background: active ? 'rgba(46,166,255,.15)' : 'rgba(255,80,80,.12)',
      color: active ? 'var(--tg)' : 'var(--danger)',
    }}>
      {status}
    </span>
  )
}

function GroupDetailSheet({ groupId, onClose, onUpdated, botUsername }) {
  const showToast = useToast()
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [status, setStatus] = useState('active')
  const [etransferEmail, setEtransferEmail] = useState('')
  const [regenSlug, setRegenSlug] = useState(false)

  const load = useCallback(async () => {
    if (!groupId) return
    setLoading(true)
    try {
      const d = await api.platform.group(groupId)
      setDetail(d)
      setName(d.group?.name || '')
      setStatus(d.group?.status || 'active')
      setEtransferEmail(d.group?.etransfer_email || '')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [groupId, showToast])

  useEffect(() => { load() }, [load])

  async function save() {
    setSaving(true)
    try {
      const r = await api.platform.patchGroup(groupId, {
        name: name.trim(),
        status,
        etransfer_email: etransferEmail.trim() || null,
        regenerate_slug: regenSlug,
      })
      setDetail(r)
      setName(r.group?.name || name)
      setRegenSlug(false)
      showToast('Group updated', 'success')
      onUpdated?.()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  async function removeMember(telegramId) {
    if (!confirm('Remove this member from the group?')) return
    try {
      await api.platform.patchUser(telegramId, { group_id: null })
      showToast('Member removed', 'success')
      load()
      onUpdated?.()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  const slug = detail?.group?.slug
  const inviteUrl = slug && botUsername
    ? `https://t.me/${botUsername}?startapp=join_${slug}` : null

  return (
    <Sheet open={!!groupId} onClose={onClose} title={detail?.group?.name || 'Group'}>
      {loading ? (
        <div style={{ padding: 32, display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
      ) : !detail ? (
        <p style={{ padding: 16, color: 'var(--tx-2)' }}>Group not found.</p>
      ) : (
        <div className="col gap-12" style={{ paddingBottom: 24 }}>
          <div className="card" style={{ padding: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--tx-3)', marginBottom: 8 }}>TRUSTEE</div>
            <div className="row gap-12" style={{ alignItems: 'center' }}>
              <TelegramAvatar user={{
                full_name: detail.group.trustee_name,
                username: detail.group.trustee_username,
                photo_url: detail.group.trustee_photo_url,
              }} size={48} />
              <div className="col gap-2 grow">
                <span style={{ fontWeight: 700 }}>{detail.group.trustee_name || detail.group.trustee_username}</span>
                <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>ID {detail.group.trustee_user_id}</span>
              </div>
            </div>
          </div>

          <div className="card col gap-10" style={{ padding: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx-3)', textTransform: 'uppercase' }}>Edit group</div>
            <label className="col gap-4">
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Group name</span>
              <input className="input" value={name} onChange={e => setName(e.target.value)} />
            </label>
            <label className="col gap-4">
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Status</span>
              <select className="input" value={status} onChange={e => setStatus(e.target.value)}>
                <option value="active">Active</option>
                <option value="suspended">Suspended (inactive)</option>
              </select>
            </label>
            <label className="col gap-4">
              <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>E-transfer email (optional)</span>
              <input className="input mono" type="email" value={etransferEmail}
                onChange={e => setEtransferEmail(e.target.value)}
                placeholder="trustee@example.com" />
            </label>
            <label className="row gap-8" style={{ alignItems: 'center', fontSize: 12 }}>
              <input type="checkbox" checked={regenSlug} onChange={e => setRegenSlug(e.target.checked)} />
              Regenerate invite slug from new name
            </label>
            <div style={{ fontSize: 11, color: 'var(--tx-3)' }}>
              Slug: <span className="mono">{slug}</span>
              {inviteUrl && (
                <div style={{ marginTop: 6, wordBreak: 'break-all' }}>{inviteUrl}</div>
              )}
            </div>
            <button className="btn btn-primary" disabled={saving || !name.trim()} onClick={save}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </div>

          <div>
            <div className="row between" style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>
                Members ({detail.members?.length ?? 0})
              </span>
              <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>{detail.rounds_count} rounds</span>
            </div>
            <div className="col gap-6">
              {(detail.members || []).map(m => (
                <div key={m.telegram_id} className="card row gap-10" style={{ padding: 10, alignItems: 'center' }}>
                  <TelegramAvatar user={m} size={36} />
                  <div className="col grow gap-2" style={{ minWidth: 0 }}>
                    <div className="row gap-6" style={{ alignItems: 'center' }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{m.full_name || m.username}</span>
                      {m.is_trustee && (
                        <span className="chip chip-gold" style={{ fontSize: 9, padding: '2px 6px' }}>TRUSTEE</span>
                      )}
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>
                      {m.email || 'no email'} · {fmtCAD(m.credit)}
                    </span>
                  </div>
                  {!m.is_trustee && (
                    <button className="btn btn-ghost btn-sm" onClick={() => removeMember(m.telegram_id)}>
                      Remove
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Sheet>
  )
}

function UserEditSheet({ user, groups, onClose, onUpdated }) {
  const showToast = useToast()
  const [groupId, setGroupId] = useState(user?.group_id ?? '')
  const [isAdmin, setIsAdmin] = useState(!!user?.is_platform_admin)
  const [credit, setCredit] = useState(String(user?.credit ?? 0))
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!user) return
    setGroupId(user.group_id ?? '')
    setIsAdmin(!!user.is_platform_admin)
    setCredit(String(user.credit ?? 0))
  }, [user])

  if (!user) return null

  async function save() {
    setSaving(true)
    try {
      await api.platform.patchUser(user.telegram_id, {
        group_id: groupId === '' ? null : Number(groupId),
        is_platform_admin: isAdmin,
        credit: parseFloat(credit) || 0,
      })
      showToast('User updated', 'success')
      onUpdated?.()
      onClose()
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Sheet open onClose={onClose} title={user.full_name || user.username || 'User'}>
      <div className="col gap-12" style={{ paddingBottom: 20 }}>
        <div style={{ fontSize: 12, color: 'var(--tx-2)' }}>Telegram ID: {user.telegram_id}</div>
        <label className="col gap-4">
          <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Group</span>
          <select className="input" value={groupId} onChange={e => setGroupId(e.target.value)}>
            <option value="">No group</option>
            {groups.map(g => (
              <option key={g.id} value={g.id}>{g.name} ({g.slug})</option>
            ))}
          </select>
        </label>
        <label className="col gap-4">
          <span style={{ fontSize: 12, color: 'var(--tx-2)' }}>Wallet balance (CAD)</span>
          <input className="input mono" type="number" step="0.01" value={credit} onChange={e => setCredit(e.target.value)} />
        </label>
        <label className="row gap-8" style={{ alignItems: 'center', fontSize: 13 }}>
          <input type="checkbox" checked={isAdmin} onChange={e => setIsAdmin(e.target.checked)} />
          Platform administrator
        </label>
        <button className="btn btn-primary" disabled={saving} onClick={save}>
          {saving ? 'Saving…' : 'Save user'}
        </button>
      </div>
    </Sheet>
  )
}

export default function PlatformAdmin() {
  const showToast = useToast()
  const botUsername = import.meta.env.VITE_BOT_USERNAME ?? ''
  const [tab, setTab] = useState('overview')
  const [overview, setOverview] = useState(null)
  const [applications, setApplications] = useState([])
  const [groups, setGroups] = useState([])
  const [users, setUsers] = useState([])
  const [rounds, setRounds] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedGroupId, setSelectedGroupId] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [userGroupFilter, setUserGroupFilter] = useState('')

  useEffect(() => {
    api.platform.groups().then(r => setGroups(r.groups || [])).catch(() => {})
  }, [])

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
        const params = { limit: 200 }
        if (userGroupFilter) params.group_id = userGroupFilter
        const r = await api.platform.users(params)
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
  }, [tab, showToast, userGroupFilter])

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
        <p style={{ fontSize: 12, color: 'var(--tx-2)', margin: 0 }}>Manage groups, members, and users</p>
      </div>

      <div style={{ padding: '0 16px 12px', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {TABS.map(t => (
          <button
            key={t}
            type="button"
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
                <button type="button" className="btn btn-primary btn-sm" onClick={() => approve(a.id)}>Approve</button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => reject(a.id)}>Reject</button>
              </div>
            </div>
          ))}
        </div>
      ) : tab === 'groups' ? (
        <div className="stack">
          {groups.length === 0 ? (
            <p style={{ padding: 16, color: 'var(--tx-2)', fontSize: 13 }}>No groups yet.</p>
          ) : groups.map(g => (
            <button
              key={g.id}
              type="button"
              className="card"
              style={{ padding: 14, textAlign: 'left', width: '100%', cursor: 'pointer' }}
              onClick={() => setSelectedGroupId(g.id)}
            >
              <div className="row between">
                <span style={{ fontWeight: 600, color: 'var(--tx-1)' }}>{g.name}</span>
                <StatusChip status={g.status} />
              </div>
              <div style={{ fontSize: 12, color: 'var(--tx-2)', marginTop: 4 }}>
                Trustee: {g.trustee_name || g.trustee_username} · {g.member_count} members
              </div>
              <div style={{ fontSize: 11, color: 'var(--tx-3)', marginTop: 2 }} className="mono">{g.slug}</div>
            </button>
          ))}
        </div>
      ) : tab === 'users' ? (
        <>
          <div style={{ padding: '0 16px 10px' }}>
            <select className="input" value={userGroupFilter} onChange={e => setUserGroupFilter(e.target.value)}>
              <option value="">All groups</option>
              {groups.map(g => (
                <option key={g.id} value={g.id}>{g.name}</option>
              ))}
            </select>
          </div>
          <div className="stack">
            {users.map(u => (
              <button
                key={u.telegram_id}
                type="button"
                className="card"
                style={{ padding: 12, textAlign: 'left', width: '100%' }}
                onClick={() => setSelectedUser(u)}
              >
                <div className="row gap-10" style={{ alignItems: 'center' }}>
                  <TelegramAvatar user={u} size={36} />
                  <div className="col grow gap-2">
                    <span style={{ fontWeight: 500, color: 'var(--tx-1)' }}>{u.full_name || u.username}</span>
                    <span style={{ fontSize: 11, color: 'var(--tx-3)' }}>
                      {u.group_name || 'No group'} · {fmtCAD(u.credit)}
                      {u.is_platform_admin ? ' · ADMIN' : ''}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </>
      ) : (
        <div className="stack">
          {rounds.map(r => (
            <div key={r.id} className="card" style={{ padding: 12 }}>
              <div className="font-weight-600" style={{ fontWeight: 600 }}>Round #{r.id} · {r.group_name}</div>
              <div style={{ fontSize: 11, color: 'var(--tx-3)' }}>
                {r.status} · pool {fmtCAD(r.pool)} · {r.participants_count} players
              </div>
            </div>
          ))}
        </div>
      )}

      <GroupDetailSheet
        groupId={selectedGroupId}
        onClose={() => setSelectedGroupId(null)}
        onUpdated={load}
        botUsername={botUsername}
      />

      <UserEditSheet
        user={selectedUser}
        groups={groups}
        onClose={() => setSelectedUser(null)}
        onUpdated={load}
      />
    </div>
  )
}
