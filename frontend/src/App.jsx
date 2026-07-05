import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './hooks/useAuth'
import Login from './pages/Login'
import Register from './pages/Register'
import Survey from './pages/Survey'
import Dashboard from './pages/Dashboard'
import Resume from './pages/Resume'
import JobFinder from './pages/JobFinder'
import InterviewList from './pages/InterviewList'
import InterviewChat from './pages/InterviewChat'
import InterviewReport from './pages/InterviewReport'

function ProtectedRoute({ children }) {
  const { token, loading } = useAuth()

  if (loading) return null

  if (!token) {
    return <Navigate to="/login" replace />
  }

  return children
}

function SurveyGuard({ children }) {
  const { token, surveyCompleted, loading } = useAuth()

  if (loading) return null

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (!surveyCompleted) {
    return <Navigate to="/survey" replace />
  }

  return children
}

function GuestRoute({ children }) {
  const { token, surveyCompleted, loading } = useAuth()

  if (loading) return null

  if (token) {
    return <Navigate to={surveyCompleted ? '/' : '/survey'} replace />
  }

  return children
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
        <Route path="/register" element={<GuestRoute><Register /></GuestRoute>} />
        <Route path="/survey" element={<ProtectedRoute><Survey /></ProtectedRoute>} />
        <Route path="/" element={<SurveyGuard><Dashboard /></SurveyGuard>} />
        <Route path="/resume" element={<SurveyGuard><Resume /></SurveyGuard>} />
        <Route path="/jobs" element={<SurveyGuard><JobFinder /></SurveyGuard>} />
        <Route path="/interview" element={<SurveyGuard><InterviewList /></SurveyGuard>} />
        <Route path="/interview/:id" element={<SurveyGuard><InterviewChat /></SurveyGuard>} />
        <Route path="/interview/:id/report" element={<SurveyGuard><InterviewReport /></SurveyGuard>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  )
}
