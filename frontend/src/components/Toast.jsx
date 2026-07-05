import { useState, useCallback, useEffect } from 'react'
import styles from './Toast.module.css'

let showGlobalToast = null

export function showToast(message, type = 'success') {
  if (showGlobalToast) showGlobalToast(message, type)
}

export default function Toast() {
  const [state, setState] = useState({ message: '', type: 'success', visible: false })

  useEffect(() => {
    showGlobalToast = (message, type) => {
      setState({ message, type, visible: true })
      setTimeout(() => setState((s) => ({ ...s, visible: false })), 3000)
    }
    return () => { showGlobalToast = null }
  }, [])

  return (
    <div className={`${styles.toast} ${styles[state.type]} ${state.visible ? styles.show : ''}`}>
      {state.message}
    </div>
  )
}
