export const STORE_ACCESS_TOKEN = 'store_access_token'
export const STORE_ID_TOKEN = 'store_id_token'
export const STORE_EXPIRES_AT = 'store_token_expires_at'
export const STORE_AUTH_NOTICE = 'store_auth_notice'
export const STORE_PKCE_VERIFIER = 'store_pkce_verifier'
export const STORE_OAUTH_STATE = 'store_oauth_state'
export const STORE_RETURN_PATH = 'store_return_path'

export type StoreAuthNotice = 'expired' | 'reauthenticate'

const STORE_AUTH_KEYS = [STORE_ACCESS_TOKEN, STORE_ID_TOKEN, STORE_EXPIRES_AT]

export function clearLegacyStoreAuth(local: Pick<Storage, 'removeItem'>) {
  for (const key of STORE_AUTH_KEYS) local.removeItem(key)
}

export function clearSessionStoreAuth(session: Pick<Storage, 'removeItem'>) {
  for (const key of STORE_AUTH_KEYS) session.removeItem(key)
}

export function clearStoreLoginAttempt(session: Pick<Storage, 'removeItem'>) {
  session.removeItem(STORE_PKCE_VERIFIER)
  session.removeItem(STORE_OAUTH_STATE)
  session.removeItem(STORE_RETURN_PATH)
}

export function clearAllStoreAuth(
  session: Pick<Storage, 'removeItem'>,
  local: Pick<Storage, 'removeItem'>,
) {
  clearSessionStoreAuth(session)
  clearLegacyStoreAuth(local)
}

export function saveStoreAccessToken(
  session: Pick<Storage, 'setItem' | 'removeItem'>,
  accessToken: string,
  expiresInSeconds: number,
  now = Date.now(),
) {
  if (!accessToken || !Number.isFinite(expiresInSeconds) || expiresInSeconds <= 0) {
    throw new Error('Cognitoトークンの応答が正しくありません')
  }

  const expiresAt = now + expiresInSeconds * 1000 - 30_000
  if (expiresAt <= now) throw new Error('Cognitoトークンの有効期間が短すぎます')

  clearSessionStoreAuth(session)
  try {
    session.setItem(STORE_ACCESS_TOKEN, accessToken)
    session.setItem(STORE_EXPIRES_AT, String(expiresAt))
  } catch (error) {
    clearSessionStoreAuth(session)
    throw error
  }
}

export function readStoreAccessToken(
  session: Pick<Storage, 'getItem' | 'removeItem'>,
  now = Date.now(),
): { token: string | null; expired: boolean } {
  const token = session.getItem(STORE_ACCESS_TOKEN)
  const expiresAt = Number(session.getItem(STORE_EXPIRES_AT) ?? 0)
  if (!token) {
    clearSessionStoreAuth(session)
    return { token: null, expired: false }
  }
  if (!Number.isFinite(expiresAt) || now >= expiresAt) {
    clearSessionStoreAuth(session)
    return { token: null, expired: true }
  }
  return { token, expired: false }
}
