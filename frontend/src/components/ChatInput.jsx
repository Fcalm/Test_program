import { useState, useRef, useEffect } from 'react'
import { Send, Paperclip, Mic, Square, FileText, X } from 'lucide-react'
import styles from './ChatInput.module.css'

export default function ChatInput({
  onSend,
  onStop,
  streaming = false,
  disabled,
  placeholder = '输入消息...',
  showActions = false,
  onUpload,
  attachments,
  onRemoveAttachment,
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
    if (!trimmed || streaming) return
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
        {attachments?.length > 0 && (
          <div className={styles.attachmentBar}>
            {attachments.map((file, i) => (
              <div key={i} className={styles.fileTag}>
                <FileText size={14} />
                <span className={styles.fileName}>{file.name}</span>
                {file.size && <span className={styles.fileSize}>{file.size}</span>}
                {onRemoveAttachment && (
                  <button
                    className={styles.fileRemove}
                    onClick={() => onRemoveAttachment(i)}
                    title="移除"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className={styles.inputRow}>
          <textarea
            ref={textareaRef}
            className={styles.input}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={streaming ? 'AI 正在回复...' : placeholder}
            disabled={disabled || streaming}
            rows={1}
          />
          {streaming ? (
            <button
              className={styles.stopBtn}
              onClick={onStop}
              title="停止输出"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              className={styles.send}
              onClick={handleSend}
              disabled={disabled || !text.trim()}
            >
              <Send size={18} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
