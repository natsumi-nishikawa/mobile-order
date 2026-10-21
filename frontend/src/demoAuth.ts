import { API_ORIGIN } from './apiConfig'

export { API_ORIGIN }
export const CUSTOMER_API = `${API_ORIGIN}/api/customer`
export const STAFF_API = `${API_ORIGIN}/api/staff`
export const ADMIN_API = `${API_ORIGIN}/api/admin`

const DEMO_AUTH_API = `${API_ORIGIN}/api/demo-auth`
const CSRF_KEY = 'demo_csrf_token'
export const DEMO_AUTH_EXPIRED_EVENT = 'demo-auth-expired'

type DemoSession = { authenticated: true; expires_at: number; csrf_token: string }

function saveSession(session: DemoSession) {
  sessionStorage.setItem(CSRF_KEY, session.csrf_token)
}

export function clearDemoSession() {
  sessionStorage.removeItem(CSRF_KEY)
}

function notifyExpired() {
  clearDemoSession()
  window.dispatchEvent(new Event(DEMO_AUTH_EXPIRED_EVENT))
}

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}))
  return typeof data.detail === 'string' ? data.detail : fallback
}

export async function loginDemo(password: string) {
  const response = await fetch(`${DEMO_AUTH_API}/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) throw new Error(await responseError(response, 'デモ認証に失敗しました'))
  const session: DemoSession = await response.json()
  saveSession(session)
  return session
}

export async function restoreDemoSession(): Promise<boolean> {
  const response = await fetch(`${DEMO_AUTH_API}/session`, { credentials: 'include' })
  if (response.status === 401) {
    clearDemoSession()
    return false
  }
  if (!response.ok) throw new Error(await responseError(response, 'デモ認証を確認できませんでした'))
  saveSession(await response.json())
  return true
}

export async function logoutDemo() {
  const csrfToken = sessionStorage.getItem(CSRF_KEY)
  const response = await fetch(`${DEMO_AUTH_API}/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: csrfToken ? { 'X-CSRF-Token': csrfToken } : {},
  })
  if (!response.ok && response.status !== 401) {
    throw new Error(await responseError(response, 'デモからログアウトできませんでした'))
  }
  clearDemoSession()
}

export async function protectedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrfToken = sessionStorage.getItem(CSRF_KEY)
    if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  }

  const response = await fetch(input, { ...init, credentials: 'include', headers })
  if (response.status === 401) {
    try {
      if (!await restoreDemoSession()) notifyExpired()
    } catch {
      // Preserve the original API response. A network/server error is not proof
      // that the demo session expired.
    }
  }
  return response
}
