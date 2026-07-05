import { createContext, useContext, useState, useEffect } from 'react'
import { apiJson } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('token'))
  const [user, setUser] = useState(null)
  const [surveyCompleted, setSurveyCompleted] = useState(() => {
    return localStorage.getItem('surveyCompleted') === 'true'
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!token) {
      setLoading(false)
      return
    }

    apiJson('/auth/me')
      .then((data) => {
        setUser(data)
        setSurveyCompleted(data.survey_completed || localStorage.getItem('surveyCompleted') === 'true')
      })
      .catch(() => {
        localStorage.removeItem('token')
        setToken(null)
      })
      .finally(() => setLoading(false))
  }, [token])

  const login = (newToken) => {
    localStorage.setItem('token', newToken)
    setToken(newToken)
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('surveyCompleted')
    setToken(null)
    setUser(null)
    setSurveyCompleted(false)
  }

  const completeSurvey = () => {
    localStorage.setItem('surveyCompleted', 'true')
    setSurveyCompleted(true)
  }

  return (
    <AuthContext.Provider value={{ token, user, surveyCompleted, loading, login, logout, completeSurvey, setUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
