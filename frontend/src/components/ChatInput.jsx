import { useState, useRef, useEffect } from 'react'
import { Send, Paperclip, Mic } from 'lucide-react'
import styles from './ChatInput.module.css'

export default function ChatInput({
  onSend,
  disabled,
  placeholder = '输入消息...',
  showActions = false,
  onUpload,
}) {
  const [text, setText] = useState('')
  const textareaRef = useRef(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }, [text])

  const handleSend = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className={styles.wrapper}>
      {showActions && (
        <div className={styles.actions}>
          <button
            className={styles.actionBtn}
            onClick={onUpload}
            title="上传文件"
            type="button"
          >
            <Paperclip size={18} />
          </button>
          <button
            className={styles.actionBtn}
            title="语音输入"
            type="button"
          >
            <Mic size={18} />
          </button>
        </div>
      )}
      <div className={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          className={styles.input}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
        />
        <button
          className={styles.send}
          onClick={handleSend}
          disabled={disabled || !text.trim()}
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}
