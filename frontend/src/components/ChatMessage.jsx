import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { FileText } from 'lucide-react'
import styles from './ChatMessage.module.css'
import ThinkingAnimation from './ThinkingAnimation'

export default function ChatMessage({ role, content, thinking, attachments, children }) {
  const isUser = role === 'user'
  const isLoading = !content && !thinking && role === 'assistant'

  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.ai}`}>
      <div className={`${styles.avatar} ${isUser ? styles.userAvatar : styles.aiAvatar}`}>
        {isUser ? 'U' : 'A'}
      </div>
      <div className={styles.content}>
        {attachments?.length > 0 && (
          <div className={styles.attachments}>
            {attachments.map((file, i) => (
              <div key={i} className={styles.fileTag}>
                <FileText size={14} />
                <span className={styles.fileName}>{file.name}</span>
                {file.size && <span className={styles.fileSize}>{file.size}</span>}
              </div>
            ))}
          </div>
        )}
        {thinking && (
          <details className={styles.thinking} open>
            <summary>思考过程</summary>
            <div className={styles.thinkingContent}>{thinking}</div>
          </details>
        )}
        {isLoading ? (
          <ThinkingAnimation />
        ) : content ? (
          <div className={`${styles.text} ${!isUser ? styles.markdown : ''}`}>
            {isUser ? content : (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            )}
          </div>
        ) : null}
        {children}
      </div>
    </div>
  )
}
