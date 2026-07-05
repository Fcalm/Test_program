import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Clock, Lightbulb, BarChart3, Loader2, X } from 'lucide-react'
import { apiJson, apiFetch } from '../lib/api'
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
  const { send, abort, streaming } = useSSE()
  const messagesEnd = useRef(null)

  const [messages, setMessages] = useState([])
  const [jdContent, setJdContent] = useState('') // 保存 JD 内容
  const [round, setRound] = useState(1)
  const [tips, setTips] = useState('')
  const [showTips, setShowTips] = useState(false)
  const [timer, setTimer] = useState(0)
  const [interviewEnded, setInterviewEnded] = useState(false)
  const [score, setScore] = useState(null)
  const [showEndModal, setShowEndModal] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportData, setReportData] = useState(null) // 分析报告数据
  const timerRef = useRef(null)

  // 分析队列机制：保证上一轮分析完成后再开始下一轮
  const analysisQueueRef = useRef([])
  const isAnalysisProcessingRef = useRef(false)

  // 计时器：每秒递增
  useEffect(() => {
    timerRef.current = setInterval(() => {
      setTimer((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timerRef.current)
  }, [])

  // 加载会话历史消息
  useEffect(() => {
    apiJson(`/agent/sessions/${id}/load`)
      .then((data) => {
        const rawMessages = data.messages || []
        let isFirstUserMsg = true
        let maxRound = 1
        let ended = false

        const formatted = rawMessages
          .filter((msg) => {
            // 保存第一条 user 消息（JD）但不显示
            if (msg.role === 'user' && isFirstUserMsg) {
              isFirstUserMsg = false
              setJdContent(msg.content || '')
              return false
            }
            // 过滤工具调用和工具结果
            if (msg.role === 'tool') return false
            if (msg.role === 'assistant') {
              if (msg.tool_calls && msg.tool_calls.length > 0) return false
              if (!msg.content && !msg.thinking) return false
            }
            return true
          })
          .map((msg) => {
            if (msg.role === 'system') {
              // 解析轮次和结束标记
              const content = msg.content || ''
              const roundMatch = content.match(/第\s*(\d+)\s*轮/)
              if (roundMatch) maxRound = Math.max(maxRound, parseInt(roundMatch[1]))
              if (content.includes('面试结束') || content.includes('interview_end')) ended = true
              return null
            }
            return { role: msg.role, content: msg.content || '', thinking: msg.thinking || '' }
          })
          .filter(Boolean)

        setMessages(formatted)
        setRound(maxRound)
        if (ended) {
          setInterviewEnded(true)
          clearInterval(timerRef.current)
          setShowEndModal(true)
        }
      })
      .catch((err) => {
        console.error('加载会话失败:', err)
        showToast('加载历史消息失败', 'error')
      })
  }, [id])

  // 自动滚动到底部
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 分析队列处理函数
  const processAnalysisQueue = async () => {
    if (isAnalysisProcessingRef.current || analysisQueueRef.current.length === 0) return

    isAnalysisProcessingRef.current = true
    const task = analysisQueueRef.current.shift()

    try {
      const result = await apiJson('/analysis/trigger', {
        method: 'POST',
        body: JSON.stringify(task),
      })
      // 更新报告数据
      if (result.report_data) {
        setReportData(result.report_data)
      }
    } catch (err) {
      // 静默失败，不影响面试流程
      console.warn('分析请求失败（已静默）:', err.message)
    } finally {
      isAnalysisProcessingRef.current = false
      // 继续处理队列中的下一个任务
      processAnalysisQueue()
    }
  }

  // 将分析任务加入队列
  const enqueueAnalysis = (analysisType, roundNum) => {
    // 收集当前聊天消息（过滤后的）
    const chatMessages = messages
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .map(m => ({
        role: m.role,
        content: m.content || '',
      }))

    analysisQueueRef.current.push({
      interview_session_id: id,
      analysis_type: analysisType,
      round: roundNum,
      messages: chatMessages,
    })

    processAnalysisQueue()
  }

  const handleSend = async (text) => {
    if (interviewEnded) return

    const userMsg = { role: 'user', content: text }
    // 立即添加一个空的 assistant 消息来显示加载动画
    const loadingMsg = { role: 'assistant', content: '', thinking: '' }
    setMessages((prev) => [...prev, userMsg, loadingMsg])

    let thinking = ''
    let content = ''

    await send('/agent/chat/stream', {
      message: text,
      session_id: id,
      scenario: 'interview',
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
          const currentRound = data.data?.round ?? round
          const nextRound = currentRound + 1
          setMessages((prev) => [
            ...prev,
            { role: 'system', type: 'round_end', round: nextRound },
          ])
          setRound(nextRound)
          setTips('')
          setShowTips(false)
          // 触发当前轮次分析（静默，队列机制）
          enqueueAnalysis('round', currentRound)
        } else if (data.type === 'interview_end') {
          setInterviewEnded(true)
          setScore(data.data?.score ?? null)
          clearInterval(timerRef.current)
          setShowEndModal(true)
          // 触发最终汇总分析（静默，队列机制）
          enqueueAnalysis('final', 0)
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
          {/* TODO: 测试用，完成后删除 */}
          <button
            className={styles.tipsBtn}
            onClick={async () => {
              setInterviewEnded(true)
              clearInterval(timerRef.current)
              setShowEndModal(true)
              setReportLoading(true)

              try {
                // 收集当前聊天消息
                const chatMessages = messages
                  .filter(m => m.role === 'user' || m.role === 'assistant')
                  .map(m => ({ role: m.role, content: m.content || '' }))

                const result = await apiJson('/analysis/trigger', {
                  method: 'POST',
                  body: JSON.stringify({
                    interview_session_id: id,
                    analysis_type: 'round',
                    round: round,
                    messages: chatMessages,
                  }),
                })
                if (result.report_data) {
                  setReportData(result.report_data)
                  showToast('分析完成', 'success')
                }
              } catch (err) {
                showToast('分析失败: ' + (err.message || '未知错误'), 'error')
              } finally {
                setReportLoading(false)
              }
            }}
            title="测试弹窗+分析"
          >
            测
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

          return (
            <ChatMessage
              key={i}
              role={msg.role}
              content={msg.content}
            />
          )
        })}
        <div ref={messagesEnd} />
      </div>

      {/* 底部输入区 */}
      <ChatInput
        onSend={handleSend}
        onStop={abort}
        streaming={streaming}
        disabled={interviewEnded}
        placeholder={interviewEnded ? '面试已结束' : '输入你的回答...'}
      />

      {/* 面试结束弹窗 */}
      {showEndModal && (
        <div className={styles.modalOverlay} onClick={() => setShowEndModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <button className={styles.modalClose} onClick={() => setShowEndModal(false)}>
              <X size={18} />
            </button>

            {reportLoading ? (
              // 加载状态
              <>
                <div className={styles.modalIcon}>
                  <Loader2 size={32} className={styles.spin} />
                </div>
                <h3 className={styles.modalTitle}>正在生成分析报告</h3>
                <p className={styles.modalHint}>AI 正在分析面试表现，请稍候...</p>
              </>
            ) : reportData ? (
              // 报告数据
              <>
                <div className={styles.modalIcon}>
                  <BarChart3 size={32} />
                </div>
                <h3 className={styles.modalTitle}>{reportData.title || '面试分析报告'}</h3>
                <div className={styles.modalTime}>
                  <Clock size={16} />
                  <span>用时 {formatTime(timer)}</span>
                </div>
                <div className={styles.modalScore}>
                  <span className={styles.modalScoreLabel}>综合评分</span>
                  <span className={styles.modalScoreValue}>{reportData.total_score}</span>
                </div>
                <div className={styles.reportDimensions}>
                  {Object.entries(reportData.dimensions || {}).map(([key, dim]) => (
                    <div key={key} className={styles.dimensionItem}>
                      <span className={styles.dimensionLabel}>{
                        {professional: '专业能力', expression: '表达能力', star: 'STAR法则', requirement: '需求理解', thinking: '思维深度'}[key] || key
                      }</span>
                      <span className={styles.dimensionScore}>{dim.score}/{dim.max}</span>
                    </div>
                  ))}
                </div>
                <button
                  className={styles.modalReportBtn}
                  onClick={() => {
                    // TODO: 跳转到详细报告页面
                    console.log('完整报告:', reportData)
                    showToast('详细报告功能开发中', 'info')
                  }}
                >
                  <BarChart3 size={16} />
                  查看详细报告
                </button>
              </>
            ) : (
              // 初始状态
              <>
                <div className={styles.modalIcon}>
                  <BarChart3 size={32} />
                </div>
                <h3 className={styles.modalTitle}>面试结束</h3>
                <div className={styles.modalTime}>
                  <Clock size={16} />
                  <span>用时 {formatTime(timer)}</span>
                </div>
                {score != null && (
                  <div className={styles.modalScore}>
                    <span className={styles.modalScoreLabel}>综合评分</span>
                    <span className={styles.modalScoreValue}>{score}</span>
                  </div>
                )}
                <p className={styles.modalHint}>点击查看详细的面试分析报告</p>
                <button
                  className={styles.modalReportBtn}
                  onClick={() => navigate(`/interview/${id}/report`)}
                >
                  <BarChart3 size={16} />
                  查看分析报告
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <Toast />
    </div>
  )
}
