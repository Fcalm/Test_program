import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { User } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { apiJson } from '../lib/api'
import Toast, { showToast } from '../components/Toast'
import styles from './Auth.module.css'

export default function Register() {
  const navigate = useNavigate()
  const { login } = useAuth()
  const [form, setForm] = useState({ username: '', email: '', password: '', confirm: '' })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [strength, setStrength] = useState(0)

  const checkStrength = (pwd) => {
    let s = 0
    if (pwd.length >= 6) s++
    if (pwd.length >= 10) s++
    if (/[A-Z]/.test(pwd)) s++
    if (/[0-9]/.test(pwd)) s++
    if (/[^A-Za-z0-9]/.test(pwd)) s++
    setStrength(Math.min(s, 4))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const newErrors = {}

    if (form.username.trim().length < 3) newErrors.username = '用户名至少3个字符'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) newErrors.email = '请输入有效的邮箱地址'
    if (form.password.length < 6) newErrors.password = '密码至少6个字符'
    if (form.password !== form.confirm) newErrors.confirm = '两次密码不一致'

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors)
      return
    }

    setErrors({})
    setLoading(true)

    try {
      await apiJson('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          username: form.username.trim(),
          email: form.email.trim(),
          password: form.password,
        }),
      })

      const loginData = await apiJson('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: form.username.trim(), password: form.password }),
      })

      login(loginData.access_token)
      showToast('注册成功！正在跳转...', 'success')

      setTimeout(() => navigate('/survey'), 1000)
    } catch (err) {
      showToast(err.message || '注册失败', 'error')
    } finally {
      setLoading(false)
    }
  }

  const strengthLabel = ['', '弱', '中', '强', '很强']
  const strengthColor = ['', 'var(--error)', 'var(--warning)', 'var(--success)', 'var(--success)']

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
          <h2 className={styles.title}>创建账号</h2>
          <p className={styles.desc}>注册后即可使用AI求职助手</p>

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
              <label className={styles.label}>邮箱</label>
              <input
                type="email"
                className={`${styles.input} ${errors.email ? styles.inputError : ''}`}
                placeholder="请输入邮箱地址"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
              {errors.email && <div className={styles.error}>{errors.email}</div>}
            </div>

            <div className={styles.group}>
              <label className={styles.label}>密码</label>
              <div className={styles.passwordWrapper}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className={`${styles.input} ${errors.password ? styles.inputError : ''}`}
                  placeholder="请输入密码（至少6位）"
                  value={form.password}
                  onChange={(e) => {
                    setForm({ ...form, password: e.target.value })
                    checkStrength(e.target.value)
                  }}
                />
                <button
                  type="button"
                  className={styles.toggle}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  {showPassword ? '🙈' : '👁'}
                </button>
              </div>
              {form.password && (
                <>
                  <div className={styles.strengthBars}>
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={styles.strengthBar}
                        style={{
                          background: i <= strength ? strengthColor[strength] : 'var(--gray-200)',
                        }}
                      />
                    ))}
                  </div>
                  <div className={styles.strengthText} style={{ color: strengthColor[strength] }}>
                    {strengthLabel[strength]}
                  </div>
                </>
              )}
              {errors.password && <div className={styles.error}>{errors.password}</div>}
            </div>

            <div className={styles.group}>
              <label className={styles.label}>确认密码</label>
              <div className={styles.passwordWrapper}>
                <input
                  type={showPassword ? 'text' : 'password'}
                  className={`${styles.input} ${errors.confirm ? styles.inputError : ''}`}
                  placeholder="请再次输入密码"
                  value={form.confirm}
                  onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                />
              </div>
              {errors.confirm && <div className={styles.error}>{errors.confirm}</div>}
            </div>

            <button type="submit" className={styles.submit} disabled={loading}>
              {loading ? <span className={styles.spinner} /> : '注册'}
            </button>
          </form>

          <div className={styles.divider}>
            <span>或</span>
          </div>

          <p className={styles.link}>
            已有账号？ <Link to="/login">立即登录</Link>
          </p>
        </div>
      </div>
      <Toast />
    </div>
  )
}
