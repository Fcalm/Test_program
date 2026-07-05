import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, ArrowLeft, ArrowRight, Check } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { apiFetch } from '../lib/api'
import Toast, { showToast } from '../components/Toast'
import styles from './Survey.module.css'

const questions = [
  {
    id: 1,
    title: '您目前的求职状态是？',
    desc: '选择最符合您当前情况的选项',
    options: ['应届毕业生', '在校学生', '在职看机会', '待业求职中', '自由职业者', '考虑转行'],
    columns: 2,
    field: 'job_status',
  },
  {
    id: 2,
    title: '您有多少年工作经验？',
    desc: '包括实习和全职工作经验',
    options: ['无经验', '1年以下', '1-3年', '3-5年', '5-10年', '10年以上'],
    columns: 2,
    field: 'experience_years',
  },
  {
    id: 3,
    title: '您期望的职位类型是？',
    desc: '可多选，选择您感兴趣的领域',
    options: ['前端开发', '后端开发', '全栈开发', '移动端开发', '数据分析师', '产品经理', 'UI/UX设计', '项目管理'],
    columns: 2,
    multi: true,
    field: 'target_positions',
  },
  {
    id: 4,
    title: '您的期望月薪是？',
    desc: '选择您期望的薪资范围（税前）',
    options: ['5K以下', '5K-10K', '10K-15K', '15K-25K', '25K-40K', '40K以上'],
    columns: 1,
    field: 'expected_salary',
  },
  {
    id: 5,
    title: '您期望的工作城市是？',
    desc: '可多选，选择您愿意工作的城市',
    options: ['北京', '上海', '深圳', '广州', '杭州', '成都', '南京', '不限'],
    columns: 2,
    multi: true,
    field: 'target_cities',
  },
  {
    id: 6,
    title: '您的最高学历是？',
    desc: '选择您已获得或正在攻读的最高学历',
    options: ['高中及以下', '大专', '本科', '硕士', '博士'],
    columns: 1,
    field: 'education_level',
  },
  {
    id: 7,
    title: '您求职时最看重什么？',
    desc: '选择您最重视的因素',
    options: ['薪资待遇', '职业发展空间', '工作生活平衡', '公司文化氛围', '技术成长学习', '工作稳定性'],
    columns: 1,
    field: 'job_priority',
  },
]

export default function Survey() {
  const navigate = useNavigate()
  const { completeSurvey } = useAuth()
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState({})
  const [done, setDone] = useState(false)

  const q = questions[current]
  const total = questions.length
  const selected = answers[q.id]

  const handleSelect = (option) => {
    if (q.multi) {
      const arr = Array.isArray(selected) ? [...selected] : []
      const idx = arr.indexOf(option)
      if (idx >= 0) arr.splice(idx, 1)
      else arr.push(option)
      setAnswers({ ...answers, [q.id]: arr })
    } else {
      setAnswers({ ...answers, [q.id]: option })
    }
  }

  const isSelected = (option) => {
    if (q.multi) return Array.isArray(selected) && selected.includes(option)
    return selected === option
  }

  const canNext = q.multi ? Array.isArray(selected) && selected.length > 0 : !!selected

  const handleNext = async () => {
    if (current < total - 1) {
      setCurrent(current + 1)
    } else {
      const profileData = {}
      for (const question of questions) {
        const ans = answers[question.id]
        profileData[question.field] = question.multi
          ? (Array.isArray(ans) ? ans : ans ? [ans] : null)
          : (ans || null)
      }

      try {
        await apiFetch('/auth/profile', {
          method: 'PUT',
          body: JSON.stringify(profileData),
        })
      } catch {
        // 即使保存失败也继续
      }

      localStorage.setItem('surveyAnswers', JSON.stringify(answers))
      completeSurvey()
      setDone(true)
      showToast('问卷完成！', 'success')
    }
  }

  const handlePrev = () => {
    if (current > 0) setCurrent(current - 1)
  }

  const handleSkip = () => {
    localStorage.setItem('surveyCompleted', 'skipped')
    navigate('/')
  }

  if (done) {
    return (
      <div className={styles.page}>
        <div className={styles.container}>
          <div className={styles.completeCard}>
            <div className={styles.completeIcon}>
              <Check size={32} color="var(--success)" />
            </div>
            <h2 className={styles.completeTitle}>问卷完成！</h2>
            <p className={styles.completeDesc}>感谢您的配合，我们将根据您的信息提供更精准的求职建议</p>
            <button className={styles.completeBtn} onClick={() => navigate('/')}>
              开始使用
            </button>
          </div>
        </div>
        <Toast />
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}>
            <User size={24} color="white" />
          </div>
          <h1 className={styles.logoTitle}>AI求职助手</h1>
          <p className={styles.logoSubtitle}>完善信息，获得更精准的推荐</p>
        </div>

        <div className={styles.progressSection}>
          <div className={styles.progressHeader}>
            <span className={styles.progressText}>问卷进度</span>
            <span className={styles.progressCount}>{current + 1}/{total}</span>
          </div>
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${((current + 1) / total) * 100}%` }} />
          </div>
        </div>

        <div className={styles.card} key={q.id}>
          <div className={styles.questionNumber}>问题 {q.id}/{total}</div>
          <h2 className={styles.questionTitle}>{q.title}</h2>
          <p className={styles.questionDesc}>{q.desc}</p>
          <div className={`${styles.optionsGrid} ${q.columns === 1 ? styles.single : ''}`}>
            {q.options.map((opt) => (
              <div
                key={opt}
                className={`${styles.option} ${isSelected(opt) ? styles.selected : ''}`}
                onClick={() => handleSelect(opt)}
              >
                {opt}
              </div>
            ))}
          </div>
        </div>

        <div className={styles.btnGroup}>
          <button
            className={styles.btnSecondary}
            onClick={handlePrev}
            disabled={current === 0}
          >
            <ArrowLeft size={16} /> 上一题
          </button>
          <button
            className={styles.btnPrimary}
            onClick={handleNext}
            disabled={!canNext}
          >
            {current === total - 1 ? '完成' : '下一题'}
            {current === total - 1 ? <Check size={16} /> : <ArrowRight size={16} />}
          </button>
        </div>

        <div className={styles.skip}>
          <a href="#" onClick={(e) => { e.preventDefault(); handleSkip() }}>暂时跳过，稍后完善</a>
        </div>
      </div>
      <Toast />
    </div>
  )
}
