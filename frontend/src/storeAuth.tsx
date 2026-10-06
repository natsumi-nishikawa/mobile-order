/* oxlint-disable react/only-export-components */
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'

const domain = (import.meta.env.VITE_COGNITO_DOMAIN ?? '').replace(/\/$/, '')
const clientId = import.meta.env.VITE_COGNITO_APP_CLIENT_ID ?? ''
const redirectUri = import.meta.env.VITE_COGNITO_REDIRECT_URI ?? window.location.origin
const logoutUri = import.meta.env.VITE_COGNITO_LOGOUT_URI ?? window.location.origin
const ACCESS_TOKEN = 'store_access_token'
const ID_TOKEN = 'store_id_token'
const EXPIRES_AT = 'store_token_expires_at'

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
  localStorage.removeItem(ACCESS_TOKEN); localStorage.removeItem(ID_TOKEN); localStorage.removeItem(EXPIRES_AT)
}

export function getAccessToken() {
  const token = localStorage.getItem(ACCESS_TOKEN)
  const expiresAt = Number(localStorage.getItem(EXPIRES_AT) ?? 0)
  if (!token || Date.now() >= expiresAt) { clearStoreAuth(); return null }
  return token
}

export function getStoreGroups() {
  const token = getAccessToken()
  return token ? decodePayload(token)?.['cognito:groups'] ?? [] : []
}

export async function beginStoreLogin(returnPath: string) {
  if (!domain || !clientId) throw new Error('CognitoのFrontend設定が不足しています')
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(48)))
  const challenge = base64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))))
  const state = base64Url(crypto.getRandomValues(new Uint8Array(24)))
  sessionStorage.setItem('store_pkce_verifier', verifier)
  sessionStorage.setItem('store_oauth_state', state)
  sessionStorage.setItem('store_return_path', returnPath)
  const params = new URLSearchParams({ response_type: 'code', client_id: clientId, redirect_uri: redirectUri, scope: 'openid email', code_challenge_method: 'S256', code_challenge: challenge, state })
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
  const response = await fetch(input, { ...init, headers: { ...init.headers, ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
  if (response.status === 401) clearStoreAuth()
  return response
}

export function StoreCallback() {
  const [error, setError] = useState('')
  useEffect(() => {
    const finish = async () => {
      const params = new URLSearchParams(window.location.search)
      const code = params.get('code'); const state = params.get('state')
      const verifier = sessionStorage.getItem('store_pkce_verifier')
      if (!code || !verifier || state !== sessionStorage.getItem('store_oauth_state')) throw new Error('ログイン応答を確認できません')
      const body = new URLSearchParams({ grant_type: 'authorization_code', client_id: clientId, code, redirect_uri: redirectUri, code_verifier: verifier })
      const response = await fetch(`${domain}/oauth2/token`, { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body })
      if (!response.ok) throw new Error('Cognitoトークンを取得できません')
      const tokens = await response.json()
      localStorage.setItem(ACCESS_TOKEN, tokens.access_token)
      if (tokens.id_token) localStorage.setItem(ID_TOKEN, tokens.id_token)
      localStorage.setItem(EXPIRES_AT, String(Date.now() + Number(tokens.expires_in) * 1000 - 30000))
      const returnPath = sessionStorage.getItem('store_return_path') || '/staff'
      sessionStorage.removeItem('store_pkce_verifier'); sessionStorage.removeItem('store_oauth_state'); sessionStorage.removeItem('store_return_path')
      window.location.replace(returnPath)
    }
    finish().catch((reason) => setError(reason instanceof Error ? reason.message : 'ログインできませんでした'))
  }, [])
  return <main className="store-login"><h1>店舗ログイン</h1><p>{error || 'ログイン処理中...'}</p>{error && <a href="/login">ログイン画面へ戻る</a>}</main>
}

export function StoreLogin() {
  const params = new URLSearchParams(window.location.search)
  const protectedPath = window.location.pathname.startsWith('/admin') || window.location.pathname.startsWith('/staff') ? window.location.pathname : '/staff'
  const destination = params.get('return') || protectedPath
  const [error, setError] = useState('')
  return <main className="store-login"><div className="store-login-card"><small>MOBILE ORDER</small><h1>店舗ログイン</h1><p>メールアドレスとパスワードでログインしてください。</p>{error && <p className="store-login-error">{error}</p>}<button onClick={() => beginStoreLogin(destination).catch((reason) => setError(reason.message))}>Cognitoでログイン</button></div></main>
}

export function StoreGuard({ role, children }: { role: 'admin' | 'staff'; children: ReactNode }) {
  const token = getAccessToken()
  if (!token) return <StoreLogin />
  const groups = getStoreGroups()
  const allowed = role === 'admin' ? groups.includes('admin') : groups.includes('staff') || groups.includes('admin')
  if (!allowed) return <main className="store-login"><div className="store-login-card"><h1>アクセスできません</h1><p>この画面を利用する権限がありません。</p><button onClick={logoutStore}>ログアウト</button></div></main>
  return children
}
