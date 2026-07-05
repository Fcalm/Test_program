import { useState, useEffect } from 'react'
import { Search, MapPin, Briefcase, User } from 'lucide-react'
import { apiJson, apiPost } from '../lib/api'
import Layout from '../components/Layout'
import EmptyState from '../components/EmptyState'
import Toast, { showToast } from '../components/Toast'
import styles from './JobFinder.module.css'

const JOB_TYPE_OPTIONS = ['全部', '实习', '校招', '社招']
const EXPERIENCE_OPTIONS = ['全部', '无经验', '1年以下', '1-3年', '3-5年', '5年以上']
const RESULT_TABS = [
  { key: 'all', label: '全部' },
  { key: 'high', label: '高匹配' },
  { key: 'salary', label: '薪资最高' },
]

function getScoreClass(score) {
  if (score >= 80) return styles.scoreHigh
  if (score >= 60) return styles.scoreMid
  return styles.scoreLow
}

function parseSalaryMin(salary) {
  if (!salary) return 0
  const match = salary.match(/(\d+)/)
  return match ? parseInt(match[1]) : 0
}

export default function JobFinder() {
  const [resume, setResume] = useState(null)
  const [city, setCity] = useState('')
  const [jobType, setJobType] = useState('全部')
  const [experience, setExperience] = useState('全部')
  const [keywords, setKeywords] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [activeTab, setActiveTab] = useState('all')

  useEffect(() => {
    apiJson('/resume')
      .then((data) => {
        if (data && data.basic_info) setResume(data)
      })
      .catch(() => {})
  }, [])

  const handleSearch = async () => {
    setLoading(true)
    setSearched(true)
    setActiveTab('all')
    try {
      const filters = {}
      if (city.trim()) filters.city = city.trim()
      if (jobType !== '全部') filters.job_type = jobType
      if (experience !== '全部') filters.experience = experience
      if (keywords.trim()) filters.keywords = keywords.trim()

      const data = await apiPost('/agent/job-search', { filters })
      setResults(Array.isArray(data) ? data : data?.results || [])
    } catch (err) {
      showToast(err.message || '搜索失败，请重试', 'error')
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !loading) handleSearch()
  }

  const filteredResults = (() => {
    let list = [...results]
    if (activeTab === 'high') {
      list = list.filter((r) => (r.score || 0) >= 60)
    } else if (activeTab === 'salary') {
      list.sort((a, b) => parseSalaryMin(b.salary) - parseSalaryMin(a.salary))
    }
    return list
  })()

  const skills = resume?.skills || []
  const basicInfo = resume?.basic_info || {}
  const name = basicInfo.name || resume?.name || ''
  const position = basicInfo.position || basicInfo.title || ''

  return (
    <Layout>
      <div className={styles.main}>
        {/* 简历信息 */}
        {resume && (
          <div className={styles.resumeCard}>
            <div className={styles.resumeAvatar}>
              <User size={28} color="var(--gray-400)" />
            </div>
            <div className={styles.resumeInfo}>
              <div className={styles.resumeName}>{name || '我的简历'}</div>
              {position && <div className={styles.resumeMeta}>{position}</div>}
              {skills.length > 0 && (
                <div className={styles.resumeSkills}>
                  {skills.slice(0, 8).map((s, i) => (
                    <span key={i} className={styles.skillTag}>
                      {typeof s === 'string' ? s : s.name || s}
                    </span>
                  ))}
                  {skills.length > 8 && (
                    <span className={styles.skillTag}>+{skills.length - 8}</span>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 筛选表单 */}
        <div className={styles.filterSection}>
          <div className={styles.filterGrid}>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>城市</label>
              <input
                className={styles.filterInput}
                placeholder="如：北京、上海"
                value={city}
                onChange={(e) => setCity(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>职位类型</label>
              <select
                className={styles.filterSelect}
                value={jobType}
                onChange={(e) => setJobType(e.target.value)}
              >
                {JOB_TYPE_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>经验要求</label>
              <select
                className={styles.filterSelect}
                value={experience}
                onChange={(e) => setExperience(e.target.value)}
              >
                {EXPERIENCE_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>{opt}</option>
                ))}
              </select>
            </div>
            <div className={styles.filterGroup}>
              <label className={styles.filterLabel}>关键词</label>
              <input
                className={styles.filterInput}
                placeholder="如：前端、Python、产品经理"
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                onKeyDown={handleKeyDown}
              />
            </div>
            <button
              className={styles.searchBtn}
              onClick={handleSearch}
              disabled={loading}
            >
              <Search size={16} />
              {loading ? '搜索中...' : '搜索职位'}
            </button>
          </div>
        </div>

        {/* 搜索结果 */}
        {searched && !loading && results.length > 0 && (
          <div className={styles.resultsSection}>
            <div className={styles.resultsHeader}>
              <div>
                <span className={styles.resultsTitle}>
                  搜索结果
                  <span className={styles.resultsCount}>
                    共 {results.length} 个职位
                  </span>
                </span>
              </div>
              <div className={styles.filterTabs}>
                {RESULT_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    className={`${styles.filterTab} ${activeTab === tab.key ? styles.filterTabActive : ''}`}
                    onClick={() => setActiveTab(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.jobList}>
              {filteredResults.map((job, i) => (
                <div key={i} className={styles.jobCard}>
                  <div className={styles.jobCardHeader}>
                    <div>
                      <div className={styles.jobTitle}>{job.title || '未知职位'}</div>
                      <div className={styles.jobCompany}>{job.company || '未知公司'}</div>
                    </div>
                    {job.score != null && (
                      <div className={`${styles.score} ${getScoreClass(job.score)}`}>
                        {job.score}
                        <span className={styles.scoreLabel}>匹配</span>
                      </div>
                    )}
                  </div>
                  {job.reason && <div className={styles.jobReason}>{job.reason}</div>}
                  <div className={styles.jobMeta}>
                    {job.salary && (
                      <span className={styles.metaItem}>
                        <Briefcase size={14} className={styles.metaIcon} />
                        {job.salary}
                      </span>
                    )}
                    {job.city && (
                      <span className={styles.metaItem}>
                        <MapPin size={14} className={styles.metaIcon} />
                        {job.city}
                      </span>
                    )}
                    {job.experience && (
                      <span className={styles.metaItem}>{job.experience}</span>
                    )}
                  </div>
                  {job.tags && job.tags.length > 0 && (
                    <div className={styles.jobTags}>
                      {job.tags.map((tag, j) => (
                        <span key={j} className={styles.skillTag}>{tag}</span>
                      ))}
                    </div>
                  )}
                  {job.source && <div className={styles.jobSource}>来源: {job.source}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 加载中 */}
        {loading && (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <span className={styles.loadingText}>正在搜索匹配职位...</span>
          </div>
        )}

        {/* 空状态 */}
        {searched && !loading && results.length === 0 && (
          <EmptyState
            icon={Briefcase}
            title="暂无匹配职位"
            description="试试调整筛选条件，扩大搜索范围"
          />
        )}
      </div>
      <Toast />
    </Layout>
  )
}
