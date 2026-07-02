import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Clock, Lightbulb, BarChart3 } from 'lucide-react'
import useSSE from '../hooks/useSSE'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import Toast, { showToast } from '../components/Toast'
import styles from './InterviewChat.module.css'

/** 格式化秒数为 mm:ss */
function formatTime(seconds) {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0')
  const s = (seconds % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

export default function InterviewChat() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { send, streaming } = useSSE()
  const messagesEnd = useRef(null)

  const [messages, setMessages] = useState([])
  const [round, setRound] = useState(1)
  const [tips, setTips] = useState('')
  const [showTips, setShowTips] = useState(false)
  const [timer, setTimer] = useState(0)
  const [interviewEnded, setInterviewEnded] = useState(false)
  const [score, setScore] = useState(null)
  const timerRef = useRef(null)

  // 计时器：每秒递增
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimer((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (text) => {
    if (interviewEnded) return

    const userMsg = { role: 'user', content: text }
    // 立即添加一个空的 assistant 消息来显示加载动画
    const loadingMsg = { role: 'assistant', content: '', thinking: '' }
    setMessages((prev) => [...prev, userMsg, loadingMsg])

    let thinking = ''
    let content = ''

    await send(`/interview/${id}/stream`, {
      message: text,
      history: messages.map((m) => ({ role: m.role, content: m.content })),
    }, {
      onEvent: (data) => {
        if (data.type === 'thinking') {
          thinking += data.data
          setMessages((prev) => {
            const updated = [...prev]
            updated[updated.length - 1] = { ...updated[updated.length - 1], thinking }
            return updated
          })
        } else if (data.type === 'content') {
          content += data.data
          setMessages((prev) => {
            const updated = [...prev]
            updated[updated.length - 1] = { ...updated[updated.length - 1], content }
            return updated
          })
        } else if (data.type === 'tips') {
          setTips(data.data)
          setShowTips(true)
        } else if (data.type === 'round_end') {
          const nextRound = data.data?.round ?? round + 1
          setMessages((prev) => [
            ...prev,
            { role: 'system', type: 'round_end', round: nextRound },
          ])
          setRound(nextRound)
          setTips('')
          setShowTips(false)
        } else if (data.type === 'interview_end') {
          setInterviewEnded(true)
          setScore(data.data?.score ?? null)
          clearInterval(timerRef.current)
          setMessages((prev) => [
            ...prev,
            { role: 'system', type: 'interview_end', score: data.data?.score },
          ])
        }
      },
      onDone: () => {
        // 流结束，无额外操作
      },
      onError: (err) => {
        showToast(err.message || '发送失败', 'error')
      },
    })
  }

  return (
    <div className={styles.container}>
      {/* 顶部栏 */}
      <header className={styles.header}>
        <button className={styles.backBtn} onClick={() => navigate('/interview')}>
          <ArrowLeft size={18} />
        </button>
        <h1 className={styles.title}>AI 模拟面试</h1>
        <div className={styles.headerRight}>
          <div className={styles.timer}>
            <Clock size={14} />
            <span>{formatTime(timer)}</span>
          </div>
          <button
            className={`${styles.tipsBtn} ${showTips ? styles.tipsBtnActive : ''}`}
            onClick={() => setShowTips((prev) => !prev)}
            title="提示"
          >
            <Lightbulb size={16} />
          </button>
        </div>
      </header>

      {/* 提示条 */}
      {showTips && tips && (
        <div className={styles.tipsBar}>
          <Lightbulb size={14} />
          <span>{tips}</span>
        </div>
      )}

      {/* 消息区 */}
      <div className={styles.messages}>
        {messages.length === 0 && (
          <div className={styles.welcome}>
            <h3>面试即将开始</h3>
            <p>请准备好，面试官将向你提出问题。认真思考后再作答。</p>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === 'system' && msg.type === 'round_end') {
            return (
              <div key={i} className={styles.roundCard}>
                <div className={styles.roundBadge}>第 {msg.round} 轮</div>
                <p className={styles.roundHint}>面试进入下一轮，继续加油！</p>
              </div>
            )
          }

          if (msg.role === 'system' && msg.type === 'interview_end') {
            return (
              <div key={i} className={styles.endCard}>
                <div className={styles.endIcon}>
                  <BarChart3 size={32} />
                </div>
                <h3>面试结束</h3>
                {msg.score != null && (
                  <div className={styles.scoreRow}>
                    <span className={styles.scoreLabel}>综合评分</span>
                    <span className={styles.scoreValue}>{msg.score}</span>
                  </div>
                )}
                <p className={styles.endHint}>点击下方按钮查看详细分析报告</p>
                <button
                  className={styles.reportBtn}
                  onClick={() => navigate(`/interview/${id}/report`)}
                >
                  <BarChart3 size={16} />
                  查看分析报告
                </button>
              </div>
            )
          }

          return (
            <ChatMessage
              key={i}
              role={msg.role}
              content={msg.content}
              thinking={msg.thinking}
            />
          )
        })}
        <div ref={messagesEnd} />
      </div>

      {/* 底部输入区 */}
      <ChatInput
        onSend={handleSend}
        disabled={streaming || interviewEnded}
        placeholder={interviewEnded ? '面试已结束' : '输入你的回答...'}
      />

      <Toast />
    </div>
  )
}
