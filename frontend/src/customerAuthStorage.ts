export const CUSTOMER_TOKEN = 'customer_token'
export const CUSTOMER_LEGACY_MIGRATION_CHECKED = 'customer_token_legacy_checked'
export const CUSTOMER_DEMO_BOUNDARY_EVENT = 'customer_auth_demo_boundary'
export type DemoBoundaryType = 'login' | 'logout' | 'expired'

type ReadWriteStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function safeGet(storage: Pick<Storage, 'getItem'>, key: string) {
  try {
    return storage.getItem(key)
  } catch {
    return null
  }
}

function safeRemove(storage: Pick<Storage, 'removeItem'>, key: string) {
  try {
    storage.removeItem(key)
  } catch {
    // Storage may be disabled by the browser. Authentication must still fail
    // closed instead of continuing with an unverified or partially moved JWT.
  }
}

function markLegacyMigrationChecked(session: Pick<Storage, 'setItem'>) {
  try {
    session.setItem(CUSTOMER_LEGACY_MIGRATION_CHECKED, '1')
  } catch {
    // A failed marker write is safe because the legacy token is removed below.
  }
}

export function readCustomerToken(
  session: Pick<Storage, 'getItem'> = sessionStorage,
) {
  return safeGet(session, CUSTOMER_TOKEN)
}

export function saveCustomerToken(
  token: string,
  session: ReadWriteStorage = sessionStorage,
  local: Pick<Storage, 'removeItem'> = localStorage,
) {
  if (!token) throw new Error('顧客認証情報を保存できません')

  try {
    session.setItem(CUSTOMER_TOKEN, token)
    if (session.getItem(CUSTOMER_TOKEN) !== token) {
      throw new Error('顧客認証情報を保存できません')
    }
    markLegacyMigrationChecked(session)
  } catch (error) {
    safeRemove(session, CUSTOMER_TOKEN)
    throw error instanceof Error ? error : new Error('顧客認証情報を保存できません')
  } finally {
    safeRemove(local, CUSTOMER_TOKEN)
  }
}

export function clearCustomerToken(
  session: Pick<Storage, 'setItem' | 'removeItem'> = sessionStorage,
  local: Pick<Storage, 'removeItem'> = localStorage,
) {
  safeRemove(session, CUSTOMER_TOKEN)
  safeRemove(local, CUSTOMER_TOKEN)
  markLegacyMigrationChecked(session)
}

export function clearCustomerTokenForDemoBoundary(
  type: DemoBoundaryType,
  session: Pick<Storage, 'setItem' | 'removeItem'> = sessionStorage,
  local: Pick<Storage, 'setItem' | 'removeItem'> = localStorage,
) {
  clearCustomerToken(session, local)
  try {
    local.setItem(CUSTOMER_DEMO_BOUNDARY_EVENT, JSON.stringify({ type, nonce: `${Date.now()}-${Math.random()}` }))
  } catch {
    // Other tabs will still reject the JWT when the shared demo cookie is gone.
  }
}

export function parseDemoBoundary(value: string | null): DemoBoundaryType | null {
  if (!value) return null
  try {
    const parsed: unknown = JSON.parse(value)
    if (!parsed || typeof parsed !== 'object' || !('type' in parsed)) return null
    const type = parsed.type
    return type === 'login' || type === 'logout' || type === 'expired' ? type : null
  } catch {
    return null
  }
}

export function migrateLegacyCustomerToken(
  session: ReadWriteStorage = sessionStorage,
  local: Pick<Storage, 'getItem' | 'removeItem'> = localStorage,
) {
  const currentToken = safeGet(session, CUSTOMER_TOKEN)
  if (currentToken) {
    safeRemove(local, CUSTOMER_TOKEN)
    markLegacyMigrationChecked(session)
    return currentToken
  }

  if (safeGet(session, CUSTOMER_LEGACY_MIGRATION_CHECKED) === '1') {
    safeRemove(local, CUSTOMER_TOKEN)
    return null
  }

  const legacyToken = safeGet(local, CUSTOMER_TOKEN)
  if (!legacyToken) {
    markLegacyMigrationChecked(session)
    return null
  }

  try {
    session.setItem(CUSTOMER_TOKEN, legacyToken)
    if (session.getItem(CUSTOMER_TOKEN) !== legacyToken) {
      throw new Error('顧客認証情報を移行できません')
    }
    return legacyToken
  } catch {
    safeRemove(session, CUSTOMER_TOKEN)
    return null
  } finally {
    safeRemove(local, CUSTOMER_TOKEN)
    markLegacyMigrationChecked(session)
  }
}
