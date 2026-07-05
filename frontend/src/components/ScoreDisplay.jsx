import styles from './ScoreDisplay.module.css'

export default function ScoreDisplay({ score, size = 88 }) {
  const level = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low'
  const color = level === 'high' ? 'var(--success)' : level === 'medium' ? 'var(--warning)' : 'var(--error)'

  return (
    <div
      className={`${styles.circle} ${styles[level]}`}
      style={{ width: size, height: size, borderColor: color }}
    >
      <span className={styles.value}>{score}</span>
      <span className={styles.label}>分</span>
    </div>
  )
}

export function ScoreBar({ score, label }) {
  const level = score >= 70 ? 'high' : score >= 40 ? 'medium' : 'low'
  const color = level === 'high' ? 'var(--success)' : level === 'medium' ? 'var(--warning)' : 'var(--error)'

  return (
    <div className={styles.barGroup}>
      {label && <span className={styles.barLabel}>{label}</span>}
      <div className={styles.bar}>
        <div className={styles.barFill} style={{ width: `${score}%`, background: color }} />
      </div>
      <span className={styles.barValue}>{score}</span>
    </div>
  )
}
