import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FileText,
  Upload,
  History,
  Trash2,
  Download,
  RotateCcw,
  Plus,
  HelpCircle,
  Search,
  PanelRightOpen,
  X,
} from 'lucide-react'
import { apiJson, apiFetch, apiDelete } from '../lib/api'
import useSSE from '../hooks/useSSE'
import Layout from '../components/Layout'
import ChatMessage from '../components/ChatMessage'
import ChatInput from '../components/ChatInput'
import Toast, { showToast } from '../components/Toast'
import styles from './Resume.module.css'

export default function Resume() {
  const navigate = useNavigate()
  const { send, streaming } = useSSE()
  const messagesEnd = useRef(null)
  const splitterRef = useRef(null)
  const editAreaRef = useRef(null)

  const [messages, setMessages] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [resumeData, setResumeData] = useState(null)
  const [hasResume, setHasResume] = useState(false)
  const [sessions, setSessions] = useState([])
  const [history, setHistory] = useState([])

  // UI 状态
  const [activeTab, setActiveTab] = useState('preview') // preview | edit | history | sessions
  const [previewOpen, setPreviewOpen] = useState(true)
  const [chatWidth, setChatWidth] = useState(60) // 百分比

  // 拖拽状态
  const [isDragging, setIsDragging] = useState(false)

  // 加载简历数据和会话列表
  useEffect(() => {
    apiJson('/resume')
      .then((data) => {
        if (data && data.basic_info) {
          setResumeData(data)
          setHasResume(true)
        }
      })
      .catch(() => {})

    apiJson('/agent/sessions?scenario=resume')
      .then((data) => setSessions(data.sessions || []))
      .catch(() => {})
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 拖拽调整宽度
  const handleMouseDown = useCallback((e) => {
    e.preventDefault()
    setIsDragging(true)
  }, [])

  useEffect(() => {
    if (!isDragging) return

    const handleMouseMove = (e) => {
      const container = document.querySelector(`.${styles.container}`)
      if (!container) return
      const rect = container.getBoundingClientRect()
      const percent = ((e.clientX - rect.left) / rect.width) * 100
      setChatWidth(Math.min(Math.max(percent, 30), 70))
    }

    const handleMouseUp = () => {
      setIsDragging(false)
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isDragging])

  // 发送消息
  const handleSend = async (text) => {
    const userMsg = { role: 'user', content: text }
    const loadingMsg = { role: 'assistant', content: '', thinking: '' }
    setMessages((prev) => [...prev, userMsg, loadingMsg])

    let thinking = ''
    let content = ''

    await send('/agent/chat/stream', {
      message: text,
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
        apiJson('/agent/sessions?scenario=resume')
          .then((data) => setSessions(data.sessions || []))
          .catch(() => {})
      },
      onError: (err) => {
        showToast(err.message || '发送失败', 'error')
      },
    })
  }

  // 加载会话
  const loadSession = async (id) => {
    try {
      const data = await apiJson(`/agent/sessions/${id}/load`)
      const rawMessages = data.messages || []

      const formattedMessages = rawMessages
        .filter((msg) => {
          if (msg.role === 'user') return true
          if (msg.role === 'assistant') {
            // 过滤掉有 tool_calls 的中间消息
            if (msg.tool_calls && msg.tool_calls.length > 0) return false
            // 过滤掉没有内容的消息
            if (!msg.content && !msg.thinking) return false
            return true
          }
          return false
        })
        .map((msg) => ({
          role: msg.role,
          content: msg.content || '',
          thinking: msg.thinking || '',
        }))

      setMessages(formattedMessages)
      setSessionId(id)
      setActiveTab('preview')
    } catch {
      showToast('加载会话失败', 'error')
    }
  }

  // 删除会话
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

  // 新建会话
  const newSession = () => {
    setSessionId(null)
    setMessages([])
    setActiveTab('preview')
  }

  // 加载历史版本
  const loadHistory = async () => {
    try {
      const data = await apiJson('/resume/history')
      setHistory(data)
      setActiveTab('history')
    } catch {
      showToast('加载历史失败', 'error')
    }
  }

  // 恢复历史版本
  const restoreHistory = async (id) => {
    try {
      await apiFetch(`/resume/history/${id}/restore`, { method: 'POST' })
      const data = await apiJson('/resume')
      setResumeData(data)
      showToast('版本已恢复')
      setActiveTab('preview')
    } catch {
      showToast('恢复失败', 'error')
    }
  }

  // 删除历史版本
  const deleteHistory = async (id) => {
    try {
      await apiDelete(`/resume/history/${id}`)
      setHistory((prev) => prev.filter((h) => h.id !== id))
    } catch {
      showToast('删除失败', 'error')
    }
  }

  // 导出简历
  const handleExport = async (format) => {
    try {
      const token = localStorage.getItem('token')
      const res = await fetch(`/resume/export?format=${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('导出失败')

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `resume.${format === 'pdf' ? 'pdf' : 'docx'}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // 保存简历
  const handleSave = async () => {
    if (!resumeData) {
      showToast('暂无简历数据', 'error')
      return
    }

    // 如果在编辑模式，提示用户通过对话修改
    if (activeTab === 'edit') {
      showToast('请通过左侧对话修改简历内容', 'error')
      return
    }

    try {
      await apiFetch('/resume', {
        method: 'PUT',
        body: JSON.stringify(resumeData),
      })
      showToast('保存成功')
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // 上传简历
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
    }
  }

  const quickActions = ['帮我优化简历', '根据 JD 调整简历', '生成一份新简历']

  return (
    <Layout>
      <div className={styles.container}>
        {/* ===== 左侧聊天区 ===== */}
        <div className={styles.chatSection} style={{ width: `${chatWidth}%` }}>
          {/* Header */}
          <div className={styles.chatHeader}>
            <div className={styles.chatLogo}>
              <FileText size={18} />
            </div>
            <div className={styles.chatTitleArea}>
              <div className={styles.chatTitle}>AI 简历助手</div>
              {sessionId && (
                <div className={styles.chatSessionId}>会话 #{sessionId.slice(0, 8)}</div>
              )}
            </div>
            <div className={styles.chatActions}>
              <button className={styles.iconBtn} onClick={newSession} title="新建会话">
                <Plus size={18} />
              </button>
              <button className={styles.iconBtn} title="帮助">
                <HelpCircle size={18} />
              </button>
              <button
                className={`${styles.iconBtn} ${styles.mobileToggle}`}
                onClick={() => setPreviewOpen(!previewOpen)}
                title="打开预览"
              >
                <PanelRightOpen size={18} />
              </button>
            </div>
          </div>

          {/* 消息列表 */}
          <div className={styles.messages}>
            {messages.length === 0 && (
              <div className={styles.welcome}>
                <div className={styles.welcomeIcon}>
                  <FileText size={32} color="var(--text-muted)" />
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

          {/* 输入区 */}
          <ChatInput
            onSend={handleSend}
            disabled={streaming}
            placeholder="输入您的问题..."
            showActions
            onUpload={() => document.getElementById('file-upload').click()}
          />
          <input
            id="file-upload"
            type="file"
            accept=".pdf,.docx"
            onChange={handleUpload}
            style={{ display: 'none' }}
          />
        </div>

        {/* ===== 分隔线 ===== */}
        <div
          ref={splitterRef}
          className={`${styles.splitter} ${isDragging ? styles.active : ''}`}
          onMouseDown={handleMouseDown}
        />

        {/* ===== 右侧预览区 ===== */}
        <div className={`${styles.previewSection} ${previewOpen ? styles.open : ''}`}>
          {/* Header */}
          <div className={styles.previewHeader}>
            <div className={styles.previewHeaderLeft}>
              <FileText size={18} color="var(--text-muted)" />
              <h3>简历预览</h3>
            </div>
            <div className={styles.previewActions}>
              <button className={styles.iconBtn} onClick={() => handleExport('pdf')} title="导出 PDF">
                <Download size={16} />
              </button>
              <button className={styles.iconBtn} onClick={() => handleExport('docx')} title="导出 DOCX">
                <Download size={16} />
              </button>
              <button
                className={`${styles.iconBtn} ${styles.mobileToggle}`}
                onClick={() => setPreviewOpen(false)}
                title="关闭预览"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Tab 导航 */}
          <div className={styles.tabs}>
            {[
              { key: 'preview', label: '预览' },
              { key: 'edit', label: '编辑' },
              { key: 'history', label: '历史' },
              { key: 'sessions', label: '会话' },
            ].map((tab) => (
              <button
                key={tab.key}
                className={`${styles.tab} ${activeTab === tab.key ? styles.active : ''}`}
                onClick={() => {
                  if (tab.key === 'history') loadHistory()
                  else if (tab.key === 'sessions') {
                    apiJson('/agent/sessions?scenario=resume')
                      .then((data) => setSessions(data.sessions || []))
                      .catch(() => {})
                  }
                  setActiveTab(tab.key)
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 内容区 */}
          <div className={styles.previewContent}>
            {/* 预览 Tab */}
            {activeTab === 'preview' && (
              resumeData ? (
                <div className={styles.resumePreview}>
                  <ResumePreview data={resumeData} />
                </div>
              ) : (
                <div className={styles.emptyState}>
                  <div className={styles.emptyIcon}>
                    <FileText size={24} />
                  </div>
                  <div className={styles.emptyTitle}>暂无简历数据</div>
                  <div className={styles.emptyDesc}>上传简历文件或通过对话创建简历</div>
                </div>
              )
            )}

            {/* 编辑 Tab */}
            {activeTab === 'edit' && (
              <div className={styles.editContainer}>
                <div
                  ref={editAreaRef}
                  className={styles.resumePreview}
                  contentEditable
                  suppressContentEditableWarning
                >
                  {resumeData ? <ResumePreview data={resumeData} /> : (
                    <div className={styles.emptyState}>
                      <div className={styles.emptyIcon}>
                        <FileText size={24} />
                      </div>
                      <div className={styles.emptyTitle}>暂无简历数据</div>
                      <div className={styles.emptyDesc}>请先通过对话生成简历</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 历史 Tab */}
            {activeTab === 'history' && (
              <div className={styles.historyList}>
                {history.length === 0 ? (
                  <div className={styles.emptyState}>
                    <div className={styles.emptyIcon}>
                      <History size={24} />
                    </div>
                    <div className={styles.emptyTitle}>暂无历史版本</div>
                    <div className={styles.emptyDesc}>保存简历后将自动记录历史版本</div>
                  </div>
                ) : (
                  history.map((h) => (
                    <div key={h.id} className={styles.historyItem}>
                      <div className={styles.historyInfo}>
                        <div className={styles.historyName}>{h.name || '未命名版本'}</div>
                        <div className={styles.historyDate}>{h.created_at}</div>
                      </div>
                      <div className={styles.historyActions}>
                        <button className={styles.iconBtn} onClick={() => restoreHistory(h.id)} title="恢复">
                          <RotateCcw size={14} />
                        </button>
                        <button className={styles.iconBtn} onClick={() => deleteHistory(h.id)} title="删除">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* 会话 Tab */}
            {activeTab === 'sessions' && (
              <div className={styles.sessionsList}>
                {sessions.length === 0 ? (
                  <div className={styles.emptyState}>
                    <div className={styles.emptyIcon}>
                      <FileText size={24} />
                    </div>
                    <div className={styles.emptyTitle}>暂无会话记录</div>
                    <div className={styles.emptyDesc}>开始对话后会自动保存会话</div>
                  </div>
                ) : (
                  sessions.map((s) => (
                    <div
                      key={s.session_id}
                      className={`${styles.sessionItem} ${sessionId === s.session_id ? styles.active : ''}`}
                    >
                      <div className={styles.sessionInfo} onClick={() => loadSession(s.session_id)}>
                        <div className={styles.sessionTitle}>
                          {s.stage || `会话 #${s.session_id.slice(0, 8)}`}
                        </div>
                        <div className={styles.sessionMeta}>
                          {s.turn_count} 轮 · {s.updated_at ? new Date(s.updated_at).toLocaleDateString('zh-CN') : ''}
                        </div>
                      </div>
                      <div className={styles.sessionActions}>
                        <button className={styles.iconBtn} onClick={() => deleteSession(s.session_id)} title="删除">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* 底部操作栏 - 仅在编辑模式显示 */}
          {activeTab === 'edit' && (
            <div className={styles.previewFooter}>
              <div className={styles.footerLeft}>
                <div className={styles.statusDot} />
                <span className={styles.statusText}>自动保存</span>
              </div>
              <div className={styles.footerActions}>
                <button className={styles.exportBtn} onClick={() => handleExport('html')}>
                  <Download size={14} />
                  导出
                </button>
                <button className={styles.saveBtn} onClick={handleSave}>
                  保存
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      <Toast />
    </Layout>
  )
}

// 简历预览组件
function ResumePreview({ data }) {
  if (!data) return null

  const b = data.basic_info || {}
  const edu = data.education || []
  const intern = data.internship_exp || []
  const proj = data.project_exp || []
  const strengths = data.personal_strengths || []

  return (
    <div>
      {/* 头部信息 */}
      <div className={styles.resumeHeader}>
        <div className={styles.resumeName}>{b.name || '姓名'}</div>
        <div className={styles.resumeContact}>
          {b.email && <span>{b.email}</span>}
          {b.phone && <span>{b.phone}</span>}
        </div>
      </div>

      {/* 教育经历 */}
      {edu.length > 0 && (
        <div className={styles.resumeSection}>
          <h4 className={styles.resumeSectionTitle}>教育经历</h4>
          {edu.map((e, i) => (
            <div key={i} className={styles.resumeItem}>
              <div className={styles.resumeItemHeader}>
                <div className={styles.resumeItemTitle}>
                  {e.school}{e.degree ? ` · ${e.degree}` : ''}{e.major ? ` · ${e.major}` : ''}
                </div>
                <div className={styles.resumeItemDate}>{e.time}</div>
              </div>
              {e.courses && (
                <div className={styles.resumeItemDesc}>主修课程：{e.courses}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 实习经历 */}
      {intern.length > 0 && (
        <div className={styles.resumeSection}>
          <h4 className={styles.resumeSectionTitle}>实习经历</h4>
          {intern.map((item, i) => (
            <div key={i} className={styles.resumeItem}>
              <div className={styles.resumeItemHeader}>
                <div className={styles.resumeItemTitle}>{item.role}</div>
                <div className={styles.resumeItemDate}>{item.time}</div>
              </div>
              <div className={styles.resumeItemSubtitle}>{item.company}</div>
              {item.description?.length > 0 && (
                <div className={styles.resumeItemDesc}>
                  <ul>
                    {item.description.map((d, j) => <li key={j}>{d}</li>)}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 项目经历 */}
      {proj.length > 0 && (
        <div className={styles.resumeSection}>
          <h4 className={styles.resumeSectionTitle}>项目经历</h4>
          {proj.map((item, i) => (
            <div key={i} className={styles.resumeItem}>
              <div className={styles.resumeItemHeader}>
                <div className={styles.resumeItemTitle}>
                  {item.name}{item.role ? ` | ${item.role}` : ''}
                </div>
                <div className={styles.resumeItemDate}>{item.time}</div>
              </div>
              {item.description?.length > 0 && (
                <div className={styles.resumeItemDesc}>
                  <ul>
                    {item.description.map((d, j) => <li key={j}>{d}</li>)}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 个人优势 */}
      {strengths.length > 0 && (
        <div className={styles.resumeSection}>
          <h4 className={styles.resumeSectionTitle}>个人优势</h4>
          <div className={styles.resumeItemDesc}>
            <ul>
              {strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
