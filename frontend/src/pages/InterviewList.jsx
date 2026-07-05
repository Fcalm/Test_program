import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { MessageSquare, Plus, Clock, Trash2, BarChart3, Play, FileText, ChevronDown, Check } from 'lucide-react'
import { apiJson, apiFetch, apiDelete } from '../lib/api'
import Layout from '../components/Layout'
import Modal from '../components/Modal'
import EmptyState from '../components/EmptyState'
import Toast, { showToast } from '../components/Toast'
import styles from './InterviewList.module.css'

/** 将 ISO 时间字符串格式化为简短的中文日期 */
function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMs / 3600000)
  const diffDay = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffHour < 24) return `${diffHour} 小时前`
  if (diffDay < 7) return `${diffDay} 天前`

  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

/** 根据 stage 判断会话状态 */
function getStatus(stage) {
  if (stage && stage.trim()) {
    return { label: '进行中', key: 'active' }
  }
  return { label: '准备中', key: 'pending' }
}

export default function InterviewList() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [jdContent, setJdContent] = useState('')
  const [title, setTitle] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 简历相关状态
  const [resumeData, setResumeData] = useState(null)
  const [resumeHistory, setResumeHistory] = useState([])
  const [selectedResumeId, setSelectedResumeId] = useState(null) // 选中的简历版本ID
  const [showResumePicker, setShowResumePicker] = useState(false)
  const pickerRef = useRef(null)

  useEffect(() => {
    loadSessions()

    // 加载当前简历
    apiJson('/resume')
      .then((data) => {
        if (data && data.basic_info) {
          setResumeData(data)
          setSelectedResumeId(data.id)
        }
      })
      .catch(() => {})

    // 加载简历历史版本
    apiJson('/resume/history')
      .then((data) => setResumeHistory(data || []))
      .catch(() => {})
  }, [])

  async function loadSessions() {
    try {
      setLoading(true)
      const data = await apiJson('/agent/sessions?scenario=interview')
      setSessions(data.sessions || [])
    } catch {
      showToast('加载会话列表失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  // 选择简历历史版本（只更新本地显示，不修改数据库）
  function handleSelectHistory(historyId) {
    const selected = resumeHistory.find(h => h.id === historyId)
    if (selected) {
      setSelectedResumeId(historyId)
      setResumeData(selected)
      setShowResumePicker(false)
    }
  }

  // 点击外部关闭 picker
  useEffect(() => {
    if (!showResumePicker) return
    const handleClick = (e) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target)) {
        setShowResumePicker(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showResumePicker])

  async function handleDelete(e, sessionId) {
    e.stopPropagation()
    if (!confirm('确定删除此面试记录？')) return

    try {
      await apiDelete(`/agent/sessions/${sessionId}`)
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId))
      showToast('已删除')
    } catch {
      showToast('删除失败', 'error')
    }
  }

  async function handleSubmit() {
    if (!jdContent.trim()) {
      showToast('请输入职位描述', 'error')
      return
    }

    setSubmitting(true)
    try {
      const data = await apiJson('/agent/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: `JD：${jdContent.trim()}\n简历id：${selectedResumeId}`,
          scenario: 'interview',
          title: title.trim(),
        }),
      })
      setModalOpen(false)
      setJdContent('')
      setTitle('')
      navigate(`/interview/${data.session_id}`)
    } catch {
      showToast('创建面试失败', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Layout>
      <div className={styles.page}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>AI 模拟面试</h1>
            <p className={styles.subtitle}>选择历史面试继续，或开始新的模拟面试</p>
          </div>
          <button className={styles.newBtn} onClick={() => setModalOpen(true)}>
            <Plus size={16} />
            新建面试
          </button>
        </div>

        {/* 当前简历板块 */}
        <div className={styles.resumeBar}>
          <div className={styles.resumeBarLeft}>
            <FileText size={16} />
            <span className={styles.resumeBarLabel}>当前简历</span>
          </div>
          <div className={styles.resumePickerWrap} ref={pickerRef}>
            <button
              className={styles.resumePickerBtn}
              onClick={() => setShowResumePicker((prev) => !prev)}
            >
              <span className={styles.resumePickerName}>
                {resumeData?.basic_info?.name || '暂无简历'}
              </span>
              <ChevronDown size={14} />
            </button>
            {showResumePicker && (
              <div className={styles.resumePickerDropdown}>
                {/* 当前简历 */}
                {resumeData && (
                  <div className={styles.pickerItemCurrent}>
                    <div className={styles.pickerItemName}>
                      {resumeData.basic_info?.name || '未命名'}
                      <span className={styles.pickerItemTag}>当前</span>
                    </div>
                    <Check size={14} />
                  </div>
                )}
                {/* 历史版本（排除当前版本） */}
                {resumeHistory.filter(h => h.id !== resumeData?.id).length > 0 && (
                  <>
                    <div className={styles.pickerDivider}>历史版本</div>
                    {resumeHistory.filter(h => h.id !== resumeData?.id).map((h) => (
                      <button
                        key={h.id}
                        className={styles.pickerItem}
                        onClick={() => handleSelectHistory(h.id)}
                      >
                        <div className={styles.pickerItemName}>
                          {h.basic_info?.name || h.name || '未命名版本'}
                        </div>
                        <div className={styles.pickerItemTime}>
                          {new Date(h.created_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' + new Date(h.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </button>
                    ))}
                  </>
                )}
                {!resumeData && resumeHistory.length === 0 && (
                  <div className={styles.pickerEmpty}>暂无简历，请先创建</div>
                )}
              </div>
            )}
          </div>
        </div>

        {loading ? (
          <div className={styles.loading}>加载中...</div>
        ) : sessions.length === 0 ? (
          <EmptyState
            icon={MessageSquare}
            title="暂无面试记录"
            description="粘贴职位描述，开始一场 AI 模拟面试"
          >
            <button className={styles.emptyBtn} onClick={() => setModalOpen(true)}>
              <Play size={16} />
              开始面试
            </button>
          </EmptyState>
        ) : (
          <div className={styles.grid}>
            {sessions.map((session) => {
              const status = getStatus(session.stage)
              return (
                <div
                  key={session.session_id}
                  className={styles.card}
                  onClick={() => navigate(`/interview/${session.session_id}`)}
                >
                  <div className={styles.cardHeader}>
                    <div className={styles.cardTitleRow}>
                      <h3 className={styles.cardTitle}>
                        {session.title || '面试会话'}
                      </h3>
                      <span
                        className={`${styles.statusDot} ${
                          status.key === 'active' ? styles.statusActive : styles.statusPending
                        }`}
                      />
                    </div>
                    <span className={styles.statusLabel}>{status.label}</span>
                  </div>

                  <div className={styles.cardMeta}>
                    <span className={styles.metaItem}>
                      <Clock size={14} />
                      {formatDate(session.updated_at || session.created_at)}
                    </span>
                    <span className={styles.metaItem}>
                      <MessageSquare size={14} />
                      {session.turn_count} 轮对话
                    </span>
                  </div>

                  <div className={styles.cardFooter}>
                    <button
                      className={styles.actionBtn}
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/interview/${session.session_id}`)
                      }}
                    >
                      <Play size={14} />
                      继续
                    </button>
                    <button
                      className={styles.actionBtn}
                      onClick={(e) => {
                        e.stopPropagation()
                        navigate(`/interview/${session.session_id}/report`)
                      }}
                    >
                      <BarChart3 size={14} />
                      报告
                    </button>
                    <button
                      className={styles.deleteBtn}
                      onClick={(e) => handleDelete(e, session.session_id)}
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* 新建面试弹窗 */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="新建模拟面试"
        footer={
          <>
            <button
              className={styles.cancelBtn}
              onClick={() => setModalOpen(false)}
            >
              取消
            </button>
            <button
              className={styles.submitBtn}
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? '创建中...' : '开始面试'}
            </button>
          </>
        }
      >
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>面试标题（可选）</label>
          <input
            className={styles.formInput}
            type="text"
            placeholder="例：字节跳动前端开发面试"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div className={styles.formGroup}>
          <label className={styles.formLabel}>职位描述（JD）*</label>
          <textarea
            className={styles.formTextarea}
            rows={8}
            placeholder="粘贴职位描述内容，AI 将根据 JD 进行针对性面试..."
            value={jdContent}
            onChange={(e) => setJdContent(e.target.value)}
          />
        </div>
      </Modal>

      <Toast />
    </Layout>
  )
}
