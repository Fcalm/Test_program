import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './ChatMessage.module.css'
import ThinkingAnimation from './ThinkingAnimation'

export default function ChatMessage({ role, content, thinking, children }) {
  const isUser = role === 'user'
  const isLoading = !content && !thinking && role === 'assistant'

  return (
    <div className={`${styles.message} ${isUser ? styles.user : styles.ai}`}>
      <div className={`${styles.avatar} ${isUser ? styles.userAvatar : styles.aiAvatar}`}>
        {isUser ? 'U' : 'A'}
      </div>
      <div className={styles.content}>
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
