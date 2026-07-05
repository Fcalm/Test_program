const API_BASE = ''

export async function apiFetch(path, options = {}) {
  const token = localStorage.getItem('token')
  const headers = { 'Content-Type': 'application/json', ...options.headers }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.href = '/login'
    throw new Error('未登录或登录已过期')
  }

  if (!res.ok) {
    let detail = `请求失败 (${res.status})`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch {}
    throw new Error(detail)
  }

  return res
}

export async function apiJson(path, options = {}) {
  const res = await apiFetch(path, options)
  if (res.status === 204) return null
  return res.json()
}

export async function apiPost(path, body) {
  return apiJson(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function apiPut(path, body) {
  return apiJson(path, { method: 'PUT', body: JSON.stringify(body) })
}

export async function apiDelete(path) {
  return apiJson(path, { method: 'DELETE' })
}
