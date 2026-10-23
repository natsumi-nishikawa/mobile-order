import { API_ORIGIN } from './apiConfig'
import { DemoSessionUnavailableError, clearDemoCsrfToken, readDemoCsrfToken, requireDemoCsrfToken, saveDemoCsrfToken } from './demoCsrf'

export { API_ORIGIN }
export const CUSTOMER_API = `${API_ORIGIN}/api/customer`
export const STAFF_API = `${API_ORIGIN}/api/staff`
export const ADMIN_API = `${API_ORIGIN}/api/admin`

const DEMO_AUTH_API = `${API_ORIGIN}/api/demo-auth`
export const DEMO_AUTH_EXPIRED_EVENT = 'demo-auth-expired'

type DemoSession = { authenticated: true; expires_at: number; csrf_token: string }

let authGeneration = 0
let restoreInFlight: Promise<boolean> | null = null

function saveSession(session: DemoSession) { saveDemoCsrfToken(session.csrf_token) }

export function clearDemoSession() {
  clearDemoCsrfToken()
}

export function invalidateDemoSession() {
  authGeneration += 1
  restoreInFlight = null
  clearDemoSession()
}

function notifyExpired() {
  invalidateDemoSession()
  window.dispatchEvent(new Event(DEMO_AUTH_EXPIRED_EVENT))
}

async function responseError(response: Response, fallback: string) {
  const data = await response.json().catch(() => ({}))
  return typeof data.detail === 'string' ? data.detail : fallback
}

export async function loginDemo(password: string) {
  invalidateDemoSession()
  const generation = authGeneration
  const response = await fetch(`${DEMO_AUTH_API}/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) throw new Error(await responseError(response, 'デモ認証に失敗しました'))
  const session: DemoSession = await response.json()
  if (generation !== authGeneration) throw new Error('デモ認証状態が更新されました。もう一度お試しください。')
  saveSession(session)
  return session
}

export async function restoreDemoSession(): Promise<boolean> {
  if (restoreInFlight) return restoreInFlight
  const generation = authGeneration
  const restore = async () => {
    const response = await fetch(`${DEMO_AUTH_API}/session`, { credentials: 'include' })
    if (generation !== authGeneration) throw new Error('デモ認証状態が更新されました')
    if (response.status === 401) {
      clearDemoSession()
      return false
    }
    if (!response.ok) throw new Error(await responseError(response, 'デモ認証を確認できませんでした'))
    saveSession(await response.json())
    return true
  }
  const pending = restore()
  restoreInFlight = pending
  try {
    return await pending
  } finally {
    if (restoreInFlight === pending) restoreInFlight = null
  }
}

export async function logoutDemo() {
  let csrfToken: string
  try {
    csrfToken = await requireDemoCsrfToken(restoreDemoSession)
  } catch (error) {
    invalidateDemoSession()
    if (error instanceof DemoSessionUnavailableError) return
    throw error
  }
  authGeneration += 1
  restoreInFlight = null
  const response = await fetch(`${DEMO_AUTH_API}/logout`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRF-Token': csrfToken },
  })
  if (!response.ok && response.status !== 401) {
    throw new Error(await responseError(response, 'デモからログアウトできませんでした'))
  }
  invalidateDemoSession()
}

export async function protectedFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    let csrfToken: string
    try {
      csrfToken = readDemoCsrfToken() ?? await requireDemoCsrfToken(restoreDemoSession)
    } catch (error) {
      if (error instanceof DemoSessionUnavailableError) notifyExpired()
      throw error
    }
    headers.set('X-CSRF-Token', csrfToken)
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
