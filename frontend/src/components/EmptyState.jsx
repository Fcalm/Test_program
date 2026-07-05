import styles from './EmptyState.module.css'

export default function EmptyState({ icon: Icon, title, description, children }) {
  return (
    <div className={styles.empty}>
      {Icon && <Icon size={64} className={styles.icon} />}
      {title && <div className={styles.title}>{title}</div>}
      {description && <div className={styles.desc}>{description}</div>}
      {children}
    </div>
  )
}
