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
  Edit3,
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

  // 编辑状态
  const [editData, setEditData] = useState(null)

  // 会话标题编辑状态
  const [editingSessionId, setEditingSessionId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')

  // 保存弹窗状态
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveHistoryName, setSaveHistoryName] = useState('')
  const [pendingSaveData, setPendingSaveData] = useState(null)

  // 历史标题编辑状态
  const [editingHistoryId, setEditingHistoryId] = useState(null)
  const [editingHistoryName, setEditingHistoryName] = useState('')

  // 拖拽状态
  const [isDragging, setIsDragging] = useState(false)

  // 加载简历数据和会话列表，并自动加载最近会话
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
      .then((data) => {
        const sessionsList = data.sessions || []
        setSessions(sessionsList)

        // 自动加载最近的会话
        if (sessionsList.length > 0) {
          loadSession(sessionsList[0].session_id)
        }
      })
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

  // 开始编辑会话标题
  const startEditSessionTitle = (session) => {
    setEditingSessionId(session.session_id)
    setEditingTitle(session.title || formatSessionTime(session.updated_at))
  }

  // 保存会话标题
  const saveSessionTitle = async (sessionId) => {
    try {
      // TODO: 后端需要支持更新会话标题的 API
      // 暂时只更新本地状态
      setSessions((prev) =>
        prev.map((s) =>
          s.session_id === sessionId ? { ...s, title: editingTitle } : s
        )
      )
      setEditingSessionId(null)
      setEditingTitle('')
      showToast('标题已更新')
    } catch {
      showToast('更新失败', 'error')
    }
  }

  // 取消编辑会话标题
  const cancelEditSessionTitle = () => {
    setEditingSessionId(null)
    setEditingTitle('')
  }

  // 格式化会话时间（精确到分钟）
  const formatSessionTime = (dateStr) => {
    if (!dateStr) return '未知时间'
    const date = new Date(dateStr)
    const now = new Date()
    const isToday = date.toDateString() === now.toDateString()

    if (isToday) {
      return `今天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
    }

    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === yesterday.toDateString()) {
      return `昨天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
    }

    return `${date.getMonth() + 1}月${date.getDate()}日 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
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

  // 开始编辑历史版本名称
  const startEditHistoryName = (item) => {
    setEditingHistoryId(item.id)
    setEditingHistoryName(item.name || formatHistoryTime(item.created_at))
  }

  // 保存历史版本名称
  const saveHistoryName = async (historyId) => {
    try {
      await apiFetch(`/resume/history/${historyId}/name`, {
        method: 'PUT',
        body: JSON.stringify({ name: editingHistoryName }),
      })
      setHistory((prev) =>
        prev.map((h) =>
          h.id === historyId ? { ...h, name: editingHistoryName } : h
        )
      )
      setEditingHistoryId(null)
      setEditingHistoryName('')
      showToast('标题已更新')
    } catch {
      showToast('更新失败', 'error')
    }
  }

  // 取消编辑历史版本名称
  const cancelEditHistoryName = () => {
    setEditingHistoryId(null)
    setEditingHistoryName('')
  }

  // 格式化历史时间
  const formatHistoryTime = (dateStr) => {
    if (!dateStr) return '未知时间'
    const date = new Date(dateStr)
    const now = new Date()
    const isToday = date.toDateString() === now.toDateString()

    if (isToday) {
      return `今天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
    }

    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === yesterday.toDateString()) {
      return `昨天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
    }

    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`
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

  // 打开保存弹窗
  const openSaveModal = () => {
    if (!resumeData) {
      showToast('暂无简历数据', 'error')
      return
    }

    // 生成默认名称：YYYY年MM月DD日 HH:MM
    const now = new Date()
    const defaultName = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
    setSaveHistoryName(defaultName)
    setPendingSaveData(resumeData)
    setShowSaveModal(true)
  }

  // 确认保存简历
  const confirmSave = async () => {
    if (!pendingSaveData) return

    try {
      await apiFetch('/resume', {
        method: 'PUT',
        body: JSON.stringify({
          ...pendingSaveData,
          history_name: saveHistoryName,
        }),
      })
      showToast('保存成功')
      setShowSaveModal(false)
      setPendingSaveData(null)

      // 刷新历史列表
      if (activeTab === 'history') {
        loadHistory()
      }
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // 编辑模式：保存编辑数据
  const handleEditSave = async () => {
    if (!editData) return

    // 生成默认名称
    const now = new Date()
    const defaultName = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日 ${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`
    setSaveHistoryName(defaultName)
    setPendingSaveData(editData)
    setShowSaveModal(true)
  }

  // 编辑模式：保存编辑数据
  const handleEditSave = async () => {
    if (!editData) return

    try {
      await apiFetch('/resume', {
        method: 'PUT',
        body: JSON.stringify(editData),
      })
      setResumeData(editData)
      showToast('保存成功')
    } catch (err) {
      showToast(err.message, 'error')
    }
  }

  // 编辑模式：内联编辑 - 同步 contentEditable 的文本回 editData
  const handleInlineEdit = (path, value) => {
    setEditData((prev) => {
      const next = JSON.parse(JSON.stringify(prev))
      let target = next
      for (let i = 0; i < path.length - 1; i++) {
        target = target[path[i]]
      }
      target[path[path.length - 1]] = value
      return next
    })
  }

  // 编辑模式：添加条目
  const handleAddItem = (section) => {
    const templates = {
      education: { school: '', degree: '', major: '', time: '', courses: '' },
      internship_exp: { company: '', role: '', time: '', description: [''] },
      project_exp: { name: '', role: '', time: '', description: [''] },
    }
    setEditData((prev) => {
      const next = { ...prev }
      if (section === 'personal_strengths') {
        next.personal_strengths = [...(next.personal_strengths || []), '']
      } else {
        next[section] = [...(next[section] || []), templates[section]]
      }
      return next
    })
  }

  // 编辑模式：删除条目
  const handleRemoveItem = (section, index) => {
    setEditData((prev) => {
      const next = { ...prev }
      next[section] = next[section].filter((_, i) => i !== index)
      return next
    })
  }

  // 编辑模式：添加描述条目
  const handleAddDesc = (section, itemIndex) => {
    setEditData((prev) => {
      const next = { ...prev }
      const arr = [...next[section]]
      arr[itemIndex] = { ...arr[itemIndex], description: [...(arr[itemIndex].description || []), ''] }
      next[section] = arr
      return next
    })
  }

  // 编辑模式：删除描述条目
  const handleRemoveDesc = (section, itemIndex, descIndex) => {
    setEditData((prev) => {
      const next = { ...prev }
      const arr = [...next[section]]
      arr[itemIndex] = { ...arr[itemIndex], description: arr[itemIndex].description.filter((_, i) => i !== descIndex) }
      next[section] = arr
      return next
    })
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
                  if (tab.key === 'edit' && resumeData) {
                    setEditData(JSON.parse(JSON.stringify(resumeData)))
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
              editData ? (
                <div className={styles.resumePreview}>
                  <ResumeEditor
                    data={editData}
                    onEdit={handleInlineEdit}
                    onAddItem={handleAddItem}
                    onRemoveItem={handleRemoveItem}
                    onAddDesc={handleAddDesc}
                    onRemoveDesc={handleRemoveDesc}
                  />
                </div>
              ) : (
                <div className={styles.emptyState}>
                  <div className={styles.emptyIcon}>
                    <FileText size={24} />
                  </div>
                  <div className={styles.emptyTitle}>暂无简历数据</div>
                  <div className={styles.emptyDesc}>请先通过对话生成简历</div>
                </div>
              )
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
                        {editingHistoryId === h.id ? (
                          <input
                            className={styles.historyNameInput}
                            value={editingHistoryName}
                            onChange={(e) => setEditingHistoryName(e.target.value)}
                            onBlur={() => saveHistoryName(h.id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveHistoryName(h.id)
                              if (e.key === 'Escape') cancelEditHistoryName()
                            }}
                            onClick={(e) => e.stopPropagation()}
                            autoFocus
                          />
                        ) : (
                          <div
                            className={styles.historyName}
                            onDoubleClick={() => startEditHistoryName(h)}
                            title="双击编辑标题"
                          >
                            {h.name || formatHistoryTime(h.created_at)}
                          </div>
                        )}
                        <div className={styles.historyDate}>
                          {new Date(h.created_at).toLocaleString('zh-CN')}
                        </div>
                      </div>
                      <div className={styles.historyActions}>
                        <button
                          className={styles.iconBtn}
                          onClick={(e) => {
                            e.stopPropagation()
                            startEditHistoryName(h)
                          }}
                          title="编辑标题"
                        >
                          <Edit3 size={14} />
                        </button>
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
                        {editingSessionId === s.session_id ? (
                          <input
                            className={styles.sessionTitleInput}
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onBlur={() => saveSessionTitle(s.session_id)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') saveSessionTitle(s.session_id)
                              if (e.key === 'Escape') cancelEditSessionTitle()
                            }}
                            onClick={(e) => e.stopPropagation()}
                            autoFocus
                          />
                        ) : (
                          <div
                            className={styles.sessionTitle}
                            onDoubleClick={() => startEditSessionTitle(s)}
                            title="双击编辑标题"
                          >
                            {s.title || formatSessionTime(s.updated_at)}
                          </div>
                        )}
                        <div className={styles.sessionMeta}>
                          {s.turn_count} 轮
                        </div>
                      </div>
                      <div className={styles.sessionActions}>
                        <button
                          className={styles.iconBtn}
                          onClick={(e) => {
                            e.stopPropagation()
                            startEditSessionTitle(s)
                          }}
                          title="编辑标题"
                        >
                          <Edit3 size={14} />
                        </button>
                        <button
                          className={styles.iconBtn}
                          onClick={(e) => {
                            e.stopPropagation()
                            deleteSession(s.session_id)
                          }}
                          title="删除"
                        >
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
                <button className={styles.saveBtn} onClick={handleEditSave}>
                  保存
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 保存弹窗 */}
      {showSaveModal && (
        <div className={styles.modalOverlay} onClick={() => setShowSaveModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h3>保存简历</h3>
              <button className={styles.modalClose} onClick={() => setShowSaveModal(false)}>
                <X size={18} />
              </button>
            </div>
            <div className={styles.modalBody}>
              <label className={styles.modalLabel}>版本名称</label>
              <input
                className={styles.modalInput}
                value={saveHistoryName}
                onChange={(e) => setSaveHistoryName(e.target.value)}
                placeholder="输入版本名称"
                autoFocus
              />
            </div>
            <div className={styles.modalFooter}>
              <button className={styles.cancelBtn} onClick={() => setShowSaveModal(false)}>
                取消
              </button>
              <button className={styles.confirmBtn} onClick={confirmSave}>
                保存
              </button>
            </div>
          </div>
        </div>
      )}

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

// 可编辑文本组件 - contentEditable + onBlur 同步
function Editable({ text, path, onEdit, className, placeholder, tag: Tag = 'span' }) {
  const handleBlur = (e) => {
    const newText = e.currentTarget.textContent || ''
    if (newText !== (text || '')) {
      onEdit(path, newText)
    }
  }

  return (
    <Tag
      className={`${styles.editable} ${className || ''}`}
      contentEditable
      suppressContentEditableWarning
      onBlur={handleBlur}
      data-placeholder={placeholder || '点击编辑'}
    >
      {text || ''}
    </Tag>
  )
}

// 可编辑描述列表（ul > li）
function EditableDescList({ items, section, itemIndex, onEdit, onAddDesc, onRemoveDesc }) {
  return (
    <div className={styles.resumeItemDesc}>
      <ul>
        {(items || []).map((d, j) => (
          <li key={j} className={styles.editableListItem}>
            <Editable
              text={d}
              path={[section, itemIndex, 'description', j]}
              onEdit={onEdit}
              placeholder="描述要点"
            />
            <button
              className={styles.inlineRemoveBtn}
              onClick={() => onRemoveDesc(section, itemIndex, j)}
              title="删除"
            >
              &times;
            </button>
          </li>
        ))}
      </ul>
      <button className={styles.inlineAddBtn} onClick={() => onAddDesc(section, itemIndex)}>
        + 添加描述
      </button>
    </div>
  )
}

// WYSIWYG 简历编辑器 - 与预览布局一致，文本可直接点击编辑
function ResumeEditor({ data, onEdit, onAddItem, onRemoveItem, onAddDesc, onRemoveDesc }) {
  const b = data.basic_info || {}
  const edu = data.education || []
  const intern = data.internship_exp || []
  const proj = data.project_exp || []
  const strengths = data.personal_strengths || []

  return (
    <div>
      {/* 头部信息 */}
      <div className={styles.resumeHeader}>
        <Editable
          text={b.name}
          path={['basic_info', 'name']}
          onEdit={onEdit}
          className={styles.resumeName}
          placeholder="姓名"
          tag="div"
        />
        <div className={styles.resumeContact}>
          <Editable
            text={b.email}
            path={['basic_info', 'email']}
            onEdit={onEdit}
            placeholder="邮箱"
          />
          <Editable
            text={b.phone}
            path={['basic_info', 'phone']}
            onEdit={onEdit}
            placeholder="手机号"
          />
        </div>
      </div>

      {/* 教育经历 */}
      <div className={styles.resumeSection}>
        <div className={styles.sectionTitleRow}>
          <h4 className={styles.resumeSectionTitle}>教育经历</h4>
          <button className={styles.inlineAddBtn} onClick={() => onAddItem('education')}>+ 添加</button>
        </div>
        {edu.map((e, i) => (
          <div key={i} className={styles.editableItem}>
            <button
              className={styles.itemRemoveBtn}
              onClick={() => onRemoveItem('education', i)}
              title="删除"
            >
              &times;
            </button>
            <div className={styles.resumeItemHeader}>
              <div className={styles.resumeItemTitle}>
                <Editable text={e.school} path={['education', i, 'school']} onEdit={onEdit} placeholder="学校" />
                {e.degree ? ' · ' : ''}
                <Editable text={e.degree} path={['education', i, 'degree']} onEdit={onEdit} placeholder="学位" />
                {e.major ? ' · ' : ''}
                <Editable text={e.major} path={['education', i, 'major']} onEdit={onEdit} placeholder="专业" />
              </div>
              <Editable
                text={e.time}
                path={['education', i, 'time']}
                onEdit={onEdit}
                className={styles.resumeItemDate}
                placeholder="时间"
              />
            </div>
            <div className={styles.resumeItemDesc}>
              主修课程：<Editable text={e.courses} path={['education', i, 'courses']} onEdit={onEdit} placeholder="主修课程（选填）" />
            </div>
          </div>
        ))}
      </div>

      {/* 实习经历 */}
      <div className={styles.resumeSection}>
        <div className={styles.sectionTitleRow}>
          <h4 className={styles.resumeSectionTitle}>实习经历</h4>
          <button className={styles.inlineAddBtn} onClick={() => onAddItem('internship_exp')}>+ 添加</button>
        </div>
        {intern.map((item, i) => (
          <div key={i} className={styles.editableItem}>
            <button
              className={styles.itemRemoveBtn}
              onClick={() => onRemoveItem('internship_exp', i)}
              title="删除"
            >
              &times;
            </button>
            <div className={styles.resumeItemHeader}>
              <Editable
                text={item.role}
                path={['internship_exp', i, 'role']}
                onEdit={onEdit}
                className={styles.resumeItemTitle}
                placeholder="职位"
              />
              <Editable
                text={item.time}
                path={['internship_exp', i, 'time']}
                onEdit={onEdit}
                className={styles.resumeItemDate}
                placeholder="时间"
              />
            </div>
            <Editable
              text={item.company}
              path={['internship_exp', i, 'company']}
              onEdit={onEdit}
              className={styles.resumeItemSubtitle}
              placeholder="公司名称"
              tag="div"
            />
            <EditableDescList
              items={item.description}
              section="internship_exp"
              itemIndex={i}
              onEdit={onEdit}
              onAddDesc={onAddDesc}
              onRemoveDesc={onRemoveDesc}
            />
          </div>
        ))}
      </div>

      {/* 项目经历 */}
      <div className={styles.resumeSection}>
        <div className={styles.sectionTitleRow}>
          <h4 className={styles.resumeSectionTitle}>项目经历</h4>
          <button className={styles.inlineAddBtn} onClick={() => onAddItem('project_exp')}>+ 添加</button>
        </div>
        {proj.map((item, i) => (
          <div key={i} className={styles.editableItem}>
            <button
              className={styles.itemRemoveBtn}
              onClick={() => onRemoveItem('project_exp', i)}
              title="删除"
            >
              &times;
            </button>
            <div className={styles.resumeItemHeader}>
              <div className={styles.resumeItemTitle}>
                <Editable text={item.name} path={['project_exp', i, 'name']} onEdit={onEdit} placeholder="项目名称" />
                {item.role ? ' | ' : ''}
                <Editable text={item.role} path={['project_exp', i, 'role']} onEdit={onEdit} placeholder="角色" />
              </div>
              <Editable
                text={item.time}
                path={['project_exp', i, 'time']}
                onEdit={onEdit}
                className={styles.resumeItemDate}
                placeholder="时间"
              />
            </div>
            <EditableDescList
              items={item.description}
              section="project_exp"
              itemIndex={i}
              onEdit={onEdit}
              onAddDesc={onAddDesc}
              onRemoveDesc={onRemoveDesc}
            />
          </div>
        ))}
      </div>

      {/* 个人优势 */}
      <div className={styles.resumeSection}>
        <div className={styles.sectionTitleRow}>
          <h4 className={styles.resumeSectionTitle}>个人优势</h4>
          <button className={styles.inlineAddBtn} onClick={() => onAddItem('personal_strengths')}>+ 添加</button>
        </div>
        <div className={styles.resumeItemDesc}>
          <ul>
            {strengths.map((s, i) => (
              <li key={i} className={styles.editableListItem}>
                <Editable
                  text={s}
                  path={['personal_strengths', i]}
                  onEdit={onEdit}
                  placeholder="个人优势"
                />
                <button
                  className={styles.inlineRemoveBtn}
                  onClick={() => onRemoveItem('personal_strengths', i)}
                  title="删除"
                >
                  &times;
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
