import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Briefcase, MessageSquare, User, LogOut, Settings, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { apiJson, apiPut } from '../lib/api'
import Layout from '../components/Layout'
import Modal from '../components/Modal'
import Toast, { showToast } from '../components/Toast'
import styles from './Dashboard.module.css'

const features = [
  {
    to: '/resume',
    icon: FileText,
    color: '#fef2f2',
    iconColor: '#ef4444',
    title: 'AI简历助手',
    desc: '智能简历优化、内容润色、格式调整。根据目标职位自动匹配关键词。',
    btn: '开始优化',
  },
  {
    to: '/jobs',
    icon: Briefcase,
    color: '#eff6ff',
    iconColor: '#3b82f6',
    title: 'AI岗位寻找',
    desc: '基于技能和经验智能匹配职位，实时追踪热门岗位。',
    btn: '寻找职位',
  },
  {
    to: '/interview',
    icon: MessageSquare,
    color: '#f0fdf4',
    iconColor: '#22c55e',
    title: 'AI面试官',
    desc: '模拟真实面试场景，提供专业反馈，涵盖多种面试类型。',
    btn: '开始模拟',
  },
]

const scenarios = [
  { key: 'resume', label: '简历助手' },
  { key: 'interview', label: '面试模拟' },
  { key: 'job_find', label: '求职顾问' },
  { key: 'analysis', label: '数据分析' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [configOpen, setConfigOpen] = useState(false)
  const [config, setConfig] = useState(null)
  const [providers, setProviders] = useState({})
  const [userSettings, setUserSettings] = useState(null)
  const [showApiKey, setShowApiKey] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState('')

  const loadConfig = async () => {
    try {
      const [configData, userSettingsData] = await Promise.all([
        apiJson('/agent/config'),
        apiJson('/agent/user-settings')
      ])
      setConfig(configData)
      setProviders(configData.providers || {})
      setUserSettings(userSettingsData)
      setApiKeyInput('') // 清空 API Key 输入
    } catch {
      showToast('配置加载失败', 'error')
    }
  }

  const handleOpenConfig = () => {
    setConfigOpen(true)
    loadConfig()
  }

  const handleSaveConfig = async () => {
    try {
      // 保存用户配置
      const userSettingsBody = {
        provider: userSettings.provider,
        model: userSettings.model,
        higher_model: userSettings.higher_model,
        scenario_overrides: userSettings.scenario_overrides,
      }

      // 只有当用户输入了新的 API Key 时才更新
      if (apiKeyInput) {
        userSettingsBody.api_key = apiKeyInput
      }

      await apiPut('/agent/user-settings', userSettingsBody)

      // 保存系统配置
      const systemConfigBody = {
        llm_model: config.defaults?.model || undefined,
        llm_higher_model: config.defaults?.higher_model || undefined,
        scenario_configs: config.defaults?.scenario_configs,
        log_level: config.log_level,
        debug: config.debug,
      }
      await apiPut('/agent/config', systemConfigBody)

      showToast('配置已保存')
      setConfigOpen(false)
    } catch {
      showToast('保存失败', 'error')
    }
  }

  const updateScenario = (key, field, value) => {
    setConfig((prev) => ({
      ...prev,
      defaults: {
        ...prev.defaults,
        scenario_configs: {
          ...prev.defaults?.scenario_configs,
          [key]: { ...prev.defaults?.scenario_configs?.[key], [field]: value },
        },
      },
    }))
  }

  const handleProviderChange = (providerKey) => {
    const provider = providers[providerKey]
    const defaultModel = provider?.models?.[0]?.id || ''

    setUserSettings(prev => ({
      ...prev,
      provider: providerKey,
      model: defaultModel,
      higher_model: '',
    }))
  }

  const handleModelChange = (modelId) => {
    setUserSettings(prev => ({
      ...prev,
      model: modelId,
    }))
  }

  const currentProvider = providers[userSettings?.provider || 'deepseek']
  const currentModels = currentProvider?.models || []

  return (
    <Layout onSettings={handleOpenConfig}>
      <div className={styles.main}>
        {/* 个人信息 */}
        <section className={styles.profile}>
          <div className={styles.profileContent}>
            <div className={styles.avatar}>
              <User size={40} color="var(--gray-400)" />
            </div>
            <div className={styles.info}>
              <p className={styles.greeting}>欢迎回来</p>
              <h1 className={styles.name}>{user?.username || '用户'}</h1>
              <p className={styles.title}>求职者</p>
            </div>
            <div className={styles.actions}>
              <button className={styles.btnPrimary} onClick={() => navigate('/resume')}>
                <FileText size={16} /> 我的简历
              </button>
              <button className={styles.btnSecondary} onClick={handleOpenConfig}>
                设置
              </button>
              <button className={styles.btnSecondary} onClick={() => { logout(); navigate('/login') }}>
                退出登录
              </button>
            </div>
          </div>
        </section>

        {/* 功能卡片 */}
        <section className={styles.features}>
          {features.map(({ to, icon: Icon, color, iconColor, title, desc, btn }) => (
            <div key={to} className={styles.card} onClick={() => navigate(to)}>
              <div className={styles.cardIcon} style={{ background: color }}>
                <Icon size={24} color={iconColor} />
              </div>
              <h2 className={styles.cardTitle}>{title}</h2>
              <p className={styles.cardDesc}>{desc}</p>
              <button className={styles.cardBtn}>{btn}</button>
            </div>
          ))}
        </section>
      </div>

      {/* 配置弹窗 */}
      <Modal
        open={configOpen}
        onClose={() => setConfigOpen(false)}
        title="系统配置"
        footer={
          <>
            <button className={styles.btnSecondary} onClick={() => setConfigOpen(false)}>取消</button>
            <button className={styles.btnPrimary} onClick={handleSaveConfig}>保存</button>
          </>
        }
      >
        {config && userSettings && (
          <>
            <div className={styles.configSection}>
              <div className={styles.configTitle}>LLM 服务商配置</div>

              <div className={styles.configRow}>
                <label>服务商</label>
                <select
                  value={userSettings.provider || 'deepseek'}
                  onChange={(e) => handleProviderChange(e.target.value)}
                >
                  {Object.entries(providers).map(([key, provider]) => (
                    <option key={key} value={key}>
                      {provider.name}
                    </option>
                  ))}
                </select>
              </div>

              {currentProvider?.requires_api_key && (
                <div className={styles.configRow}>
                  <label>API Key</label>
                  <div className={styles.apiKeyInput}>
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                      placeholder={userSettings.api_key_set ? '已设置（留空保持不变）' : '请输入 API Key'}
                    />
                    <button
                      className={styles.toggleBtn}
                      onClick={() => setShowApiKey(!showApiKey)}
                      type="button"
                    >
                      {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  <p className={styles.helpText}>留空使用系统默认配置</p>
                </div>
              )}

              <div className={styles.configRow}>
                <label>主模型</label>
                <select
                  value={userSettings.model || ''}
                  onChange={(e) => handleModelChange(e.target.value)}
                >
                  {currentModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.id} - {model.description}
                    </option>
                  ))}
                </select>
              </div>

              <div className={styles.configRow}>
                <label>高级模型</label>
                <select
                  value={userSettings.higher_model || ''}
                  onChange={(e) => setUserSettings(prev => ({ ...prev, higher_model: e.target.value }))}
                >
                  <option value="">不使用</option>
                  {currentModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.id} - {model.description}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className={styles.configSection}>
              <div className={styles.configTitle}>场景配置</div>
              <table className={styles.scenarioTable}>
                <thead>
                  <tr>
                    <th>场景</th>
                    <th>最大轮次</th>
                    <th>Temperature</th>
                  </tr>
                </thead>
                <tbody>
                  {scenarios.map(({ key, label }) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>
                        <input
                          type="number"
                          min="1"
                          max="20"
                          value={config.defaults?.scenario_configs?.[key]?.max_rounds || 10}
                          onChange={(e) => updateScenario(key, 'max_rounds', parseInt(e.target.value) || 10)}
                        />
                      </td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          max="2"
                          step="0.1"
                          value={config.defaults?.scenario_configs?.[key]?.temperature || 0.5}
                          onChange={(e) => updateScenario(key, 'temperature', parseFloat(e.target.value) || 0.5)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className={styles.configSection}>
              <div className={styles.configTitle}>系统配置</div>
              <div className={styles.configRow}>
                <label>日志级别</label>
                <select
                  value={config.log_level || 'INFO'}
                  onChange={(e) => setConfig({ ...config, log_level: e.target.value })}
                >
                  <option value="DEBUG">DEBUG</option>
                  <option value="INFO">INFO</option>
                  <option value="WARNING">WARNING</option>
                  <option value="ERROR">ERROR</option>
                </select>
              </div>
              <div className={styles.configRow}>
                <label>调试模式</label>
                <select
                  value={String(config.debug || false)}
                  onChange={(e) => setConfig({ ...config, debug: e.target.value === 'true' })}
                >
                  <option value="false">关闭</option>
                  <option value="true">开启</option>
                </select>
              </div>
            </div>
          </>
        )}
      </Modal>
      <Toast />
    </Layout>
  )
}