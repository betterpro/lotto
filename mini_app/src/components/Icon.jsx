const props = (extra) => ({ fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round', viewBox: '0 0 24 24', ...extra })

export const HomeIcon     = (p) => <svg {...props(p)}><path d="M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z"/><path d="M9 21V12h6v9"/></svg>
export const TicketIcon   = (p) => <svg {...props(p)}><path d="M2 9a1 1 0 011-1h18a1 1 0 011 1v2a2 2 0 000 4v2a1 1 0 01-1 1H3a1 1 0 01-1-1v-2a2 2 0 000-4V9z"/></svg>
export const ClockIcon    = (p) => <svg {...props(p)}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>
export const ShieldIcon   = (p) => <svg {...props(p)}><path d="M12 2l7 3v6c0 4.418-3.134 8.548-7 10-3.866-1.452-7-5.582-7-10V5l7-3z"/></svg>
export const WalletIcon   = (p) => <svg {...props(p)}><rect x="2" y="5" width="20" height="15" rx="2"/><path d="M16 12a1 1 0 100 2 1 1 0 000-2z" fill="currentColor" stroke="none"/><path d="M2 10h20"/></svg>
export const GiftIcon     = (p) => <svg {...props(p)}><path d="M20 12v9H4v-9"/><rect x="2" y="7" width="20" height="5" rx="1"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 010-5C10 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 000-5C14 2 12 7 12 7z"/></svg>
export const TrophyIcon   = (p) => <svg {...props(p)}><path d="M8 21h8M12 17v4"/><path d="M7 4H4v4c0 2.2 1.8 4 4 4"/><path d="M17 4h3v4c0 2.2-1.8 4-4 4"/><path d="M7 8a5 5 0 0010 0V2H7v6z"/></svg>
export const BoltIcon     = (p) => <svg {...props(p)}><path d="M13 2L4.5 13.5H12L11 22l8.5-11.5H13L13 2z" strokeWidth={1.6}/></svg>
export const PlusIcon     = (p) => <svg {...props(p)}><circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/></svg>
export const ShareIcon    = (p) => <svg {...props(p)}><path d="M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7"/><path d="M16 6l-4-4-4 4"/><path d="M12 2v13"/></svg>
export const CheckIcon    = (p) => <svg {...props(p)}><polyline points="20 6 9 17 4 12"/></svg>
export const XIcon        = (p) => <svg {...props(p)}><path d="M18 6L6 18M6 6l12 12"/></svg>
export const ChevronRight = (p) => <svg {...props(p)}><path d="M9 18l6-6-6-6"/></svg>
export const UsersIcon    = (p) => <svg {...props(p)}><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
export const BarChartIcon = (p) => <svg {...props(p)}><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6"  y1="20" x2="6"  y2="14"/><line x1="2"  y1="20" x2="22" y2="20"/></svg>
export const ArrowDownIcon= (p) => <svg {...props(p)}><path d="M12 5v14M5 12l7 7 7-7"/></svg>
export const CameraIcon   = (p) => <svg {...props(p)}><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>
export const FilterIcon   = (p) => <svg {...props(p)}><path d="M4 6h16M7 12h10M10 18h4"/></svg>
export const UploadIcon   = (p) => <svg {...props(p)}><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
export const SearchIcon   = (p) => <svg {...props(p)}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>
export const MoreIcon     = (p) => <svg viewBox="0 0 24 24" fill="currentColor" {...p}><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
export const StarIcon     = (p) => <svg {...props(p)}><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>

export const Icon = {
  Home: HomeIcon, Ticket: TicketIcon, Clock: ClockIcon, Shield: ShieldIcon,
  Wallet: WalletIcon, Gift: GiftIcon, Trophy: TrophyIcon, Bolt: BoltIcon,
  Plus: PlusIcon, Share: ShareIcon, Check: CheckIcon, X: XIcon,
  ChevronRight, Users: UsersIcon, BarChart: BarChartIcon,
  ArrowDown: ArrowDownIcon, Camera: CameraIcon,
  Filter: FilterIcon, Upload: UploadIcon, Search: SearchIcon, More: MoreIcon, Star: StarIcon,
}
