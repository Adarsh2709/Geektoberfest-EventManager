const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function api(path, options = {}) {
  const token = localStorage.getItem('eventhub_token')
  const headers = { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (response.status === 204) return null
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Something went wrong')
  return data
}

export const dateLabel = (value) => new Date(value).toLocaleDateString(undefined, {
  day: 'numeric', month: 'long', year: 'numeric',
})

export const timeLabel = (value) => new Date(value).toLocaleTimeString(undefined, {
  hour: 'numeric', minute: '2-digit',
})
