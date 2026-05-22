import { HomeIcon, TicketIcon, ClockIcon, ShieldIcon, PersonIcon } from './Icon.jsx'

const TABS = [
  { id: 'home',    Icon: HomeIcon,   label: 'Home'    },
  { id: 'rounds',  Icon: TicketIcon, label: 'Rounds'  },
  { id: 'history', Icon: ClockIcon,  label: 'Activity'},
  { id: 'profile', Icon: PersonIcon, label: 'Profile' },
  { id: 'admin',   Icon: ShieldIcon, label: 'Admin'   },
]

export default function BottomNav({ page, setPage, isTrustee }) {
  const tabs = isTrustee ? TABS : TABS.filter(t => t.id !== 'admin')
  return (
    <nav className="tabbar">
      {tabs.map(t => (
        <button key={t.id} className={page === t.id ? 'active' : ''} onClick={() => setPage(t.id)}>
          <t.Icon width={22} height={22} />
          {t.label}
        </button>
      ))}
    </nav>
  )
}
