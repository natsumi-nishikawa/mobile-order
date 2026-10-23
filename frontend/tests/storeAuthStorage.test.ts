import assert from 'node:assert/strict'
import test from 'node:test'

import {
  STORE_ACCESS_TOKEN,
  STORE_EXPIRES_AT,
  STORE_ID_TOKEN,
  STORE_OAUTH_STATE,
  STORE_PKCE_VERIFIER,
  STORE_RETURN_PATH,
  clearAllStoreAuth,
  clearLegacyStoreAuth,
  clearStoreLoginAttempt,
  readStoreAccessToken,
  saveStoreAccessToken,
} from '../src/storeAuthStorage.ts'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

test('stores only the Cognito access token and expiry in session storage', () => {
  const session = new MemoryStorage()
  saveStoreAccessToken(session, 'access-token', 3600, 1_000_000)

  assert.equal(session.getItem(STORE_ACCESS_TOKEN), 'access-token')
  assert.equal(session.getItem(STORE_EXPIRES_AT), String(1_000_000 + 3_600_000 - 30_000))
  assert.equal(session.getItem(STORE_ID_TOKEN), null)
})

test('removes legacy Cognito values instead of migrating them', () => {
  const local = new MemoryStorage()
  local.setItem(STORE_ACCESS_TOKEN, 'legacy-access-token')
  local.setItem(STORE_ID_TOKEN, 'legacy-id-token')
  local.setItem(STORE_EXPIRES_AT, '999999999')

  clearLegacyStoreAuth(local)

  assert.equal(local.getItem(STORE_ACCESS_TOKEN), null)
  assert.equal(local.getItem(STORE_ID_TOKEN), null)
  assert.equal(local.getItem(STORE_EXPIRES_AT), null)
})

test('keeps a valid session token available across page initialization', () => {
  const session = new MemoryStorage()
  saveStoreAccessToken(session, 'access-token', 3600, 1_000_000)

  assert.deepEqual(readStoreAccessToken(session, 2_000_000), {
    token: 'access-token',
    expired: false,
  })
})

test('clears an expired session token and requests reauthentication', () => {
  const session = new MemoryStorage()
  saveStoreAccessToken(session, 'access-token', 60, 1_000_000)

  assert.deepEqual(readStoreAccessToken(session, 1_030_000), {
    token: null,
    expired: true,
  })
  assert.equal(session.getItem(STORE_ACCESS_TOKEN), null)
  assert.equal(session.getItem(STORE_EXPIRES_AT), null)
})

test('logout clears both current session values and all legacy local values', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  session.setItem(STORE_ACCESS_TOKEN, 'session-access-token')
  session.setItem(STORE_ID_TOKEN, 'unexpected-session-id-token')
  session.setItem(STORE_EXPIRES_AT, '999999999')
  local.setItem(STORE_ACCESS_TOKEN, 'legacy-access-token')
  local.setItem(STORE_ID_TOKEN, 'legacy-id-token')
  local.setItem(STORE_EXPIRES_AT, '999999999')

  clearAllStoreAuth(session, local)

  for (const key of [STORE_ACCESS_TOKEN, STORE_ID_TOKEN, STORE_EXPIRES_AT]) {
    assert.equal(session.getItem(key), null)
    assert.equal(local.getItem(key), null)
  }
})

test('callback cleanup removes PKCE and OAuth temporary values after success or failure', () => {
  const session = new MemoryStorage()
  session.setItem(STORE_PKCE_VERIFIER, 'verifier')
  session.setItem(STORE_OAUTH_STATE, 'state')
  session.setItem(STORE_RETURN_PATH, '/admin')

  clearStoreLoginAttempt(session)

  assert.equal(session.getItem(STORE_PKCE_VERIFIER), null)
  assert.equal(session.getItem(STORE_OAUTH_STATE), null)
  assert.equal(session.getItem(STORE_RETURN_PATH), null)
})
