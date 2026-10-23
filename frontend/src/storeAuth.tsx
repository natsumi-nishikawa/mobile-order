/* oxlint-disable react/only-export-components */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { protectedFetch } from './demoAuth'
import { safeStoreReturnPath } from './storeRedirect'
import {
  STORE_AUTH_NOTICE,
  STORE_OAUTH_STATE,
  STORE_PKCE_VERIFIER,
  STORE_RETURN_PATH,
  clearAllStoreAuth,
  clearLegacyStoreAuth,
  clearStoreLoginAttempt,
  readStoreAccessToken,
  saveStoreAccessToken,
} from './storeAuthStorage'
import type { StoreAuthNotice } from './storeAuthStorage'

const domain = (import.meta.env.VITE_COGNITO_DOMAIN ?? '').replace(/\/$/, '')
const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID ?? ''
const redirectUri = import.meta.env.VITE_COGNITO_REDIRECT_URI ?? window.location.origin
const logoutUri = import.meta.env.VITE_COGNITO_LOGOUT_URI ?? window.location.origin
// Do not migrate bearer tokens from persistent storage. Existing users must
// authenticate again so no legacy Cognito token remains available there.
clearLegacyStoreAuth(localStorage)

type TokenPayload = { exp?: number; username?: string; sub?: string; 'cognito:groups'?: string[] }

function decodePayload(token: string): TokenPayload | null {
  try {
    const value = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(value.padEnd(Math.ceil(value.length / 4) * 4, '=')))
  } catch { return null }
}

function base64Url(bytes: Uint8Array) {
  let binary = ''
  bytes.forEach((byte) => { binary += String.fromCharCode(byte) })
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function clearStoreAuth() {
  clearAllStoreAuth(sessionStorage, localStorage)
  clearStoreLoginAttempt(sessionStorage)
  sessionStorage.removeItem(STORE_AUTH_NOTICE)
}

function requireStoreLogin(notice: StoreAuthNotice) {
  clearAllStoreAuth(sessionStorage, localStorage)
  sessionStorage.setItem(STORE_AUTH_NOTICE, notice)
}

function loginNotice() {
  const notice = sessionStorage.getItem(STORE_AUTH_NOTICE)
  if (notice === 'expired') return 'ログインの有効期限が切れました。Cognitoで再ログインしてください。'
  if (notice === 'reauthenticate') return '認証を確認できませんでした。Cognitoで再ログインしてください。'
  return ''
}

export function getAccessToken() {
  const result = readStoreAccessToken(sessionStorage)
  if (result.expired) requireStoreLogin('expired')
  return result.token
}

export function getStoreGroups() {
  const token = getAccessToken()
  return token ? decodePayload(token)?.['cognito:groups'] ?? [] : []
}

export async function beginStoreLogin(returnPath: string) {
  if (!domain || !clientId) throw new Error('CognitoのFrontend設定が不足しています')
  clearAllStoreAuth(sessionStorage, localStorage)
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(48)))
  const challenge = base64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))))
  const state = base64Url(crypto.getRandomValues(new Uint8Array(24)))
  clearStoreLoginAttempt(sessionStorage)
  sessionStorage.removeItem(STORE_AUTH_NOTICE)
  sessionStorage.setItem(STORE_PKCE_VERIFIER, verifier)
  sessionStorage.setItem(STORE_OAUTH_STATE, state)
  sessionStorage.setItem(STORE_RETURN_PATH, safeStoreReturnPath(returnPath))
  const params = new URLSearchParams({ response_type: 'code', client_id: clientId, redirect_uri: redirectUri, scope: 'openid email', code_challenge_method: 'S256', code_challenge: challenge, state, lang:'ja' })
  window.location.assign(`${domain}/oauth2/authorize?${params}`)
}

export function logoutStore() {
  clearStoreAuth()
  if (!domain || !clientId) { window.location.assign('/login'); return }
  const params = new URLSearchParams({ client_id: clientId, logout_uri: logoutUri })
  window.location.assign(`${domain}/logout?${params}`)
}

export async function storeFetch(input: RequestInfo | URL, init: RequestInit = {}) {
  const token = getAccessToken()
  const headers = new Headers(init.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await protectedFetch(input, { ...init, headers })
  // A 401 with a still-valid demo session belongs to Cognito/customer auth.
  // Clearing this token is therefore safe and independent of demo auth.
  if (response.status === 401) requireStoreLogin('reauthenticate')
  return response
}

export function StoreCallback() {
  const [error, setError] = useState('')
  useEffect(() => {
    const finish = async () => {
      const params = new URLSearchParams(window.location.search)
      const code = params.get('code'); const state = params.get('state')
      const verifier = sessionStorage.getItem(STORE_PKCE_VERIFIER)
      const returnPath = sessionStorage.getItem(STORE_RETURN_PATH)
      window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.hash}`)
      try {
        const oauthError = params.get('error_description') ?? params.get('error')
        if (oauthError) throw new Error('Cognitoログインが完了しませんでした。もう一度お試しください。')
        if (!code || !verifier || state !== sessionStorage.getItem(STORE_OAUTH_STATE)) throw new Error('ログイン応答を確認できません')
        const body = new URLSearchParams({ grant_type: 'authorization_code', client_id: clientId, code, redirect_uri: redirectUri, code_verifier: verifier })
        const response = await fetch(`${domain}/oauth2/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body })
        if (!response.ok) throw new Error('Cognitoトークンを取得できません')
        const tokens: { access_token?: unknown; expires_in?: unknown } = await response.json()
        saveStoreAccessToken(sessionStorage, typeof tokens.access_token === 'string' ? tokens.access_token : '', Number(tokens.expires_in))
        clearLegacyStoreAuth(localStorage)
        sessionStorage.removeItem(STORE_AUTH_NOTICE)
        const groups = decodePayload(tokens.access_token as string)?.['cognito:groups'] ?? []
        window.location.replace(safeStoreReturnPath(returnPath, groups))
      } finally {
        clearStoreLoginAttempt(sessionStorage)
      }
    }
    finish().catch((reason) => {
      clearAllStoreAuth(sessionStorage, localStorage)
      setError(reason instanceof Error ? reason.message : 'ログインできませんでした')
    })
  }, [])
  return <main className="store-login"><h1>店舗ログイン</h1><p>{error || 'ログイン処理中...'}</p>{error && <a href="/login">ログイン画面へ戻る</a>}</main>
}

export function StoreLogin() {
  const params = new URLSearchParams(window.location.search)
  const protectedPath = safeStoreReturnPath(window.location.pathname)
  const destination = safeStoreReturnPath(params.get('return') ?? protectedPath)
  const [error, setError] = useState('')
  const notice = loginNotice()
  return <main className="store-login"><div className="store-login-card"><small>MOBILE ORDER</small><h1>店舗ログイン</h1><p>メールアドレスとパスワードでログインしてください。</p>{notice && <p className="store-login-error">{notice}</p>}{error && <p className="store-login-error">{error}</p>}<button onClick={() => beginStoreLogin(destination).catch((reason) => setError(reason.message))}>Cognitoでログイン</button></div></main>
}

export function StoreGuard({ role, children }: { role: 'admin' | 'staff'; children: ReactNode }) {
  const token = getAccessToken()
  if (!token) return <StoreLogin />
  const groups = getStoreGroups()
  const allowed = role === 'admin' ? groups.includes('admin') : groups.includes('staff') || groups.includes('admin')
  if (!allowed) return <main className="store-login"><div className="store-login-card"><h1>アクセスできません</h1><p>この画面を利用する権限がありません。</p><button onClick={logoutStore}>ログアウト</button></div></main>
  return children
}
