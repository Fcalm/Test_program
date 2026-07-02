import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Upload, History, Trash2, Download, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react'
import { apiJson, apiFetch, apiDelete } from '../lib/api'
import useSSE from '../hooks/useSSE'
import Layout from '../components/Layout'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import EmptyState from '../components/EmptyState'
import Toast, { showToast } from '../components/Toast'
import styles from './Resume.module.css'

export default function Resume() {
  const navigate = useNavigate()
  const { send, streaming } = useSSE()
  const messagesEnd = useRef(null)

  const [messages, setMessages] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [resumeData, setResumeData] = useState(null)
  const [hasResume, setHasResume] = useState(false)
  const [sessions, setSessions] = useState([])
  const [history, setHistory] = useState([])
  const [showHistory, setShowHistory] = useState(false)
  const [showSessions, setShowSessions] = useState(false)
  const [exportFormat, setExportFormat] = useState('html')
  const [uploading, setUploading] = useState(false)

  // 加载简历数据
  useEffect(() => {
    apiJson('/resume').then((data) => {
      if (data && data.basic_info) {
        setResumeData(data)
        setHasResume(true)
      }
    }).catch(() => {})

    apiJson('/agent/sessions?scenario=resume').then((data) => setSessions(data.sessions || [])).catch(() => {})
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (text) => {
    const userMsg = { role: 'user', content: text }
    // 立即添加一个空的 assistant 消息来显示加载动画
    const loadingMsg = { role: 'assistant', content: '', thinking: '' }
    setMessages((prev) => [...prev, userMsg, loadingMsg])

    let thinking = ''
    let content = ''

    await send('/agent/chat/stream', {
      message: text,
      history: messages.map((m) => ({ role: m.role, content: m.content })),
      scenario: 'resume',
      ...(sessionId ? { session_id: sessionId } : {}),
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
        } else if (data.type === 'resume') {
          setResumeData(data.data)
          setHasResume(true)
          showToast('简历已更新')
        } else if (data.type === 'done') {
          if (data.data?.session_id) {
            setSessionId(data.data.session_id)
          }
        }
      },
      onDone: () => {
        apiJson('/agent/sessions?scenario=resume').then((data) => setSessions(data.sessions || [])).catch(() => {})
      },
      onError: (err) => {
        showToast(err.message || '发送失败', 'error')
      },
    })
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    const ext = file.name.split('.').pop().toLowerCase()
    if (!['pdf', 'docx'].includes(ext)) {
      showToast('仅支持 PDF 和 DOCX 格式', 'error')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast('文件大小不能超过 10MB', 'error')
      return
    }

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const token = localStorage.getItem('token')
      const res = await fetch('/files/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })

      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || '上传失败')
      }

      showToast('文件上传成功，正在解析...')
      const data = await apiJson('/resume')
      if (data && data.basic_info) {
        setResumeData(data)
        setHasResume(true)
      }
    } catch (err) {
      showToast(err.message, 'error')
    } finally {
      setUploading(false)
    }
  }

  const handleExport = async () => {
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`/resume/export?format=${exportFormat}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('导出失败')

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `resume.${exportFormat === 'pdf' ? 'pdf' : 'docx'}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  const loadSession = async (id) => {
    try {
      const data = await apiJson(`/agent/sessions/${id}/load`)
      setMessages(data.messages || [])
      setSessionId(id)
      setShowSessions(false)
    } catch {
      showToast('加载会话失败', 'error')
    }
  }

  const deleteSession = async (id) => {
    try {
      await apiDelete(`/agent/sessions/${id}`)
      setSessions((prev) => prev.filter((s) => s.session_id !== id))
      if (sessionId === id) {
        setSessionId(null)
        setMessages([])
      }
    } catch {
      showToast('删除失败', 'error')
    }
  }

  const loadHistory = async () => {
    try {
      const data = await apiJson('/resume/history')
      setHistory(data)
      setShowHistory(true)
    } catch {
      showToast('加载历史失败', 'error')
    }
  }

  const restoreHistory = async (id) => {
    try {
      await apiFetch(`/resume/history/${id}/restore`, { method: 'POST' })
      const data = await apiJson('/resume')
      setResumeData(data)
      showToast('版本已恢复')
      setShowHistory(false)
    } catch {
      showToast('恢复失败', 'error')
    }
  }

  const deleteHistory = async (id) => {
    try {
      await apiDelete(`/resume/history/${id}`)
      setHistory((prev) => prev.filter((h) => h.id !== id))
    } catch {
      showToast('删除失败', 'error')
    }
  }

  const quickActions = [
    '帮我优化简历',
    '根据 JD 调整简历',
    '生成一份新简历',
  ]

  return (
    <Layout>
      <div className={styles.container}>
        {/* 聊天区 */}
        <div className={styles.chatSection}>
          <div className={styles.chatHeader}>
            <h2 className={styles.chatTitle}>AI 简历助手</h2>
            <div className={styles.chatActions}>
              <button
                className={styles.iconBtn}
                onClick={() => setShowSessions(!showSessions)}
                title="会话管理"
              >
                <FileText size={16} />
              </button>
              <label className={styles.iconBtn} title="上传简历">
                <Upload size={16} />
                <input
                  type="file"
                  accept=".pdf,.docx"
                  onChange={handleUpload}
                  style={{ display: 'none' }}
                />
              </label>
            </div>
          </div>

          {/* 会话列表 */}
          {showSessions && (
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <span>历史会话</span>
                <button onClick={() => setShowSessions(false)}>关闭</button>
              </div>
              {sessions.length === 0 ? (
                <div className={styles.panelEmpty}>暂无会话</div>
              ) : (
                sessions.map((s) => (
                  <div key={s.session_id} className={styles.sessionItem}>
                    <span onClick={() => loadSession(s.session_id)}>{s.title || s.stage || '未命名会话'}</span>
                    <button onClick={() => deleteSession(s.session_id)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* 消息列表 */}
          <div className={styles.messages}>
            {messages.length === 0 && (
              <div className={styles.welcome}>
                <div className={styles.welcomeIcon}>
                  <FileText size={32} color="var(--gray-400)" />
                </div>
                <h3>AI 简历助手</h3>
                <p>我可以帮你创建、优化简历，也可以根据 JD 调整内容。</p>
                <div className={styles.quickActions}>
                  {quickActions.map((action) => (
                    <button
                      key={action}
                      className={styles.quickBtn}
                      onClick={() => handleSend(action)}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <ChatMessage key={i} role={msg.role} content={msg.content} thinking={msg.thinking} />
            ))}
            <div ref={messagesEnd} />
          </div>

          <ChatInput onSend={handleSend} disabled={streaming} placeholder="描述你的简历需求..." />
        </div>

        {/* 简历预览区 */}
        <div className={styles.previewSection}>
          <div className={styles.previewHeader}>
            <h3>简历预览</h3>
            <div className={styles.previewActions}>
              <select
                value={exportFormat}
                onChange={(e) => setExportFormat(e.target.value)}
                className={styles.formatSelect}
              >
                <option value="html">HTML</option>
                <option value="pdf">PDF</option>
                <option value="docx">DOCX</option>
              </select>
              <button className={styles.iconBtn} onClick={handleExport} title="导出">
                <Download size={16} />
              </button>
              <button className={styles.iconBtn} onClick={loadHistory} title="历史版本">
                <History size={16} />
              </button>
            </div>
          </div>

          {/* 历史版本 */}
          {showHistory && (
            <div className={styles.panel}>
              <div className={styles.panelHeader}>
                <span>历史版本</span>
                <button onClick={() => setShowHistory(false)}>关闭</button>
              </div>
              {history.length === 0 ? (
                <div className={styles.panelEmpty}>暂无历史版本</div>
              ) : (
                history.map((h) => (
                  <div key={h.id} className={styles.sessionItem}>
                    <span>{h.name || h.created_at}</span>
                    <div>
                      <button onClick={() => restoreHistory(h.id)} title="恢复">
                        <RotateCcw size={14} />
                      </button>
                      <button onClick={() => deleteHistory(h.id)} title="删除">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          <div className={styles.previewContent}>
            {resumeData ? (
              <div className={styles.resumePreview}>
                <ResumePreview data={resumeData} />
              </div>
            ) : (
              <EmptyState
                icon={FileText}
                title="暂无简历数据"
                description="上传简历文件或通过对话创建简历"
              />
            )}
          </div>
        </div>
      </div>
      <Toast />
    </Layout>
  )
}

function ResumePreview({ data }) {
  if (!data) return null

  const sections = [
    { key: 'basic_info', title: '基本信息' },
    { key: 'education', title: '教育经历' },
    { key: 'experience', title: '工作经历' },
    { key: 'projects', title: '项目经历' },
    { key: 'skills', title: '技能特长' },
    { key: 'awards', title: '荣誉奖项' },
    { key: 'self_intro', title: '自我评价' },
  ]

  return (
    <div>
      {data.name && <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 16 }}>{data.name}</h2>}
      {sections.map(({ key, title }) => {
        const value = data[key]
        if (!value) return null

        if (typeof value === 'string') {
          return (
            <div key={key} style={{ marginBottom: 16 }}>
              <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 8 }}>{title}</h4>
              <p style={{ fontSize: 14, lineHeight: 1.6 }}>{value}</p>
            </div>
          )
        }

        if (Array.isArray(value)) {
          return (
            <div key={key} style={{ marginBottom: 16 }}>
              <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 8 }}>{title}</h4>
              {value.map((item, i) => (
                <div key={i} style={{ marginBottom: 8, fontSize: 14 }}>
                  {typeof item === 'string' ? item : JSON.stringify(item)}
                </div>
              ))}
            </div>
          )
        }

        if (typeof value === 'object') {
          return (
            <div key={key} style={{ marginBottom: 16 }}>
              <h4 style={{ fontSize: 14, fontWeight: 600, color: 'var(--gray-500)', marginBottom: 8 }}>{title}</h4>
              {Object.entries(value).map(([k, v]) => (
                <div key={k} style={{ marginBottom: 4, fontSize: 14 }}>
                  <strong>{k}:</strong> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </div>
              ))}
            </div>
          )
        }

        return null
      })}
    </div>
  )
}
