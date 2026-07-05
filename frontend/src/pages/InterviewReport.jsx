import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, MessageSquare } from 'lucide-react'
import Layout from '../components/Layout'
import ScoreDisplay, { ScoreBar } from '../components/ScoreDisplay'
import EmptyState from '../components/EmptyState'
import Toast, { showToast } from '../components/Toast'
import styles from './InterviewReport.module.css'

const mockReport = {
  title: '模拟面试报告',
  date: '2024-01-15',
  overallScore: 78,
  dimensions: [
    { name: '专业知识', score: 82 },
    { name: '表达能力', score: 75 },
    { name: '逻辑思维', score: 80 },
    { name: '抗压能力', score: 70 },
  ],
  questions: [
    {
      question: '请介绍一下你最复杂的项目',
      answer: '我曾经参与过一个电商平台的开发...',
      score: 80,
      strengths: ['回答结构清晰', '提到了具体技术方案'],
      suggestions: ['可以补充更多量化数据', '建议使用 STAR 法则'],
    },
    {
      question: '你如何处理团队中的技术分歧？',
      answer: '我会先了解对方的方案...',
      score: 75,
      strengths: ['态度积极', '有具体案例'],
      suggestions: ['可以补充冲突解决的具体步骤'],
    },
  ],
}

export default function InterviewReport() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 后端接口暂未实现，使用 mock 数据
    const loadReport = async () => {
      try {
        setLoading(true)
        // TODO: 替换为真实 API 调用
        // const data = await apiJson(`/agent/interview/report/${id}`)
        await new Promise((r) => setTimeout(r, 500))
        setReport(mockReport)
      } catch {
        showToast('报告加载失败', 'error')
      } finally {
        setLoading(false)
      }
    }
    loadReport()
  }, [id])

  if (loading) {
    return (
      <Layout>
        <div className={styles.loading}>加载中...</div>
      </Layout>
    )
  }

  if (!report) {
    return (
      <Layout>
        <EmptyState
          icon={MessageSquare}
          title="未找到报告"
          description="该面试报告不存在或已被删除"
        >
          <button className={styles.backBtn} onClick={() => navigate('/interview')}>
            返回面试列表
          </button>
        </EmptyState>
      </Layout>
    )
  }

  return (
    <Layout>
      <div className={styles.main}>
        {/* 返回按钮 */}
        <button className={styles.goBack} onClick={() => navigate('/interview')}>
          <ArrowLeft size={16} />
          返回面试列表
        </button>

        {/* 报告头部 */}
        <section className={styles.header}>
          <ScoreDisplay score={report.overallScore} size={88} />
          <div className={styles.headerInfo}>
            <h1 className={styles.title}>{report.title}</h1>
            <p className={styles.date}>{report.date}</p>
            <p className={styles.summary}>
              综合得分 {report.overallScore} 分，整体表现良好，建议在表达逻辑和抗压能力方面继续提升。
            </p>
          </div>
        </section>

        {/* 维度得分 */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>维度评分</h2>
          <div className={styles.dimensions}>
            {report.dimensions.map((dim) => (
              <ScoreBar key={dim.name} label={dim.name} score={dim.score} />
            ))}
          </div>
        </section>

        {/* 逐题分析 */}
        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>逐题分析</h2>
          <div className={styles.questions}>
            {report.questions.map((q, i) => (
              <div key={i} className={styles.questionCard}>
                <div className={styles.questionHeader}>
                  <span className={styles.questionIndex}>Q{i + 1}</span>
                  <span className={styles.questionText}>{q.question}</span>
                  <span className={styles.questionScore}>{q.score}分</span>
                </div>

                <div className={styles.answerBlock}>
                  <div className={styles.answerLabel}>你的回答</div>
                  <p className={styles.answerText}>{q.answer}</p>
                </div>

                <div className={styles.tags}>
                  {q.strengths.map((s, j) => (
                    <span key={`s-${j}`} className={styles.tagStrength}>{s}</span>
                  ))}
                  {q.suggestions.map((s, j) => (
                    <span key={`g-${j}`} className={styles.tagSuggestion}>{s}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>
      <Toast />
    </Layout>
  )
}
