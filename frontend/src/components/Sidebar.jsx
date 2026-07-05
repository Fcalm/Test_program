import { NavLink, useNavigate } from 'react-router-dom'
import { Home, FileText, Briefcase, MessageSquare, Settings, ArrowLeft, LogOut } from 'lucide-react'
import styles from './Sidebar.module.css'

const navItems = [
  { to: '/', icon: Home, label: '首页' },
  { to: '/resume', icon: FileText, label: '简历' },
  { to: '/jobs', icon: Briefcase, label: '职位' },
  { to: '/interview', icon: MessageSquare, label: '面试' },
]

export default function Sidebar({ onSettings }) {
  const navigate = useNavigate()

  return (
    <nav className={styles.sidebar}>
      <div className={styles.logo}>A</div>

      <button className={styles.back} onClick={() => navigate('/')} title="返回首页">
        <ArrowLeft size={20} />
      </button>

      <div className={styles.divider} />

      <div className={styles.nav}>
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) => `${styles.navItem} ${isActive ? styles.active : ''}`}
            title={label}
          >
            <Icon size={20} />
            <span className={styles.label}>{label}</span>
          </NavLink>
        ))}
      </div>

      <div className={styles.bottom}>
        {onSettings && (
          <button className={styles.navItem} onClick={onSettings} title="设置">
            <Settings size={20} />
            <span className={styles.label}>设置</span>
          </button>
        )}
      </div>
    </nav>
  )
}
