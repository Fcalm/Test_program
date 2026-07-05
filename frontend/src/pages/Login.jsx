import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { User } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { apiJson } from '../lib/api'
import Toast, { showToast } from '../components/Toast'
import styles from './Auth.module.css'

export default function Login() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [form, setForm] = useState({ username: '', password: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    const newErrors = {}

    if (!form.username.trim()) newErrors.username = '用户名不能为空'
    if (!form.password) newErrors.password = '密码不能为空'

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setErrors({})
    setLoading(true)

    try {
      const data = await apiJson('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: form.username.trim(), password: form.password }),
      })

      login(data.access_token)
      showToast('登录成功！正在跳转...', 'success')

      setTimeout(() => {
        const survey = localStorage.getItem('surveyCompleted')
        navigate(survey ? '/' : '/survey')
      }, 1000)
    } catch (err) {
      showToast(err.message || '登录失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.logo}>
          <div className={styles.logoIcon}>
            <User size={24} color="white" />
          </div>
          <h1 className={styles.logoTitle}>AI求职助手</h1>
          <p className={styles.logoSubtitle}>智能求职，高效匹配</p>
        </div>

        <div className={styles.card}>
          <h2 className={styles.title}>欢迎回来</h2>
          <p className={styles.desc}>请登录您的账号</p>

          <form onSubmit={handleSubmit}>
            <div className={styles.group}>
              <label className={styles.label}>用户名</label>
              <input
                type="text"
                className={`${styles.input} ${errors.username ? styles.inputError : ''}`}
                placeholder="请输入用户名"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
              />
              {errors.username && <div className={styles.error}>{errors.username}</div>}
            </div>

            <div className={styles.group}>
              <label className={styles.label}>密码</label>
              <div className={styles.passwordWrapper}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className={`${styles.input} ${errors.password ? styles.inputError : ''}`}
                  placeholder="请输入密码"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                />
                <button
                  type="button"
                  className={styles.toggle}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? '🙈' : '👁'}
                </button>
              </div>
              {errors.password && <div className={styles.error}>{errors.password}</div>}
            </div>

            <button type="submit" className={styles.submit} disabled={loading}>
              {loading ? <span className={styles.spinner} /> : '登录'}
            </button>
          </form>

          <div className={styles.divider}>
            <span>或</span>
          </div>

          <p className={styles.link}>
            还没有账号？ <Link to="/register">立即注册</Link>
          </p>
        </div>
      </div>
      <Toast />
    </div>
  )
}
