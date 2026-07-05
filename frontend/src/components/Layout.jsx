import Sidebar from './Sidebar'
import Toast from './Toast'
import styles from './Layout.module.css'

export default function Layout({ children, onSettings }) {
  return (
    <div className={styles.container}>
      <Sidebar onSettings={onSettings} />
      <main className={styles.main}>
        {children}
      </main>
      <Toast />
    </div>
  )
}
