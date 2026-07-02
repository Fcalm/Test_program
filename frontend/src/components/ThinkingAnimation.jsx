import styles from './ThinkingAnimation.module.css'

export default function ThinkingAnimation() {
  return (
    <div className={styles.container}>
      <div className={styles.arrow}>
        <div className={styles.segment} />
        <div className={styles.segment} />
        <div className={styles.segment} />
      </div>
      <span className={styles.text}>思考中</span>
    </div>
  )
}
