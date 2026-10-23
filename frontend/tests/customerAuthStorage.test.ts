import assert from 'node:assert/strict'
import test from 'node:test'

import {
  CUSTOMER_LEGACY_MIGRATION_CHECKED,
  CUSTOMER_DEMO_BOUNDARY_EVENT,
  CUSTOMER_TOKEN,
  clearCustomerToken,
  clearCustomerTokenForDemoBoundary,
  migrateLegacyCustomerToken,
  parseDemoBoundary,
  readCustomerToken,
  saveCustomerToken,
} from '../src/customerAuthStorage.ts'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

test('stores a newly issued customer JWT only in session storage', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()

  saveCustomerToken('new-token', session, local)

  assert.equal(session.getItem(CUSTOMER_TOKEN), 'new-token')
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
})

test('migrates a legacy JWT once and removes the local value', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  local.setItem(CUSTOMER_TOKEN, 'legacy-token')

  assert.equal(migrateLegacyCustomerToken(session, local), 'legacy-token')
  assert.equal(session.getItem(CUSTOMER_TOKEN), 'legacy-token')
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
  assert.equal(session.getItem(CUSTOMER_LEGACY_MIGRATION_CHECKED), '1')
})

test('does not overwrite an existing session JWT with a legacy JWT', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  session.setItem(CUSTOMER_TOKEN, 'current-token')
  local.setItem(CUSTOMER_TOKEN, 'legacy-token')

  assert.equal(migrateLegacyCustomerToken(session, local), 'current-token')
  assert.equal(session.getItem(CUSTOMER_TOKEN), 'current-token')
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
})

test('does not migrate a legacy JWT again after authentication was cleared', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  local.setItem(CUSTOMER_TOKEN, 'old-token')
  clearCustomerToken(session, local)
  local.setItem(CUSTOMER_TOKEN, 'unexpected-stale-token')

  assert.equal(migrateLegacyCustomerToken(session, local), null)
  assert.equal(session.getItem(CUSTOMER_TOKEN), null)
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
})

test('clearing customer authentication leaves unrelated Cognito and CSRF values intact', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  session.setItem(CUSTOMER_TOKEN, 'customer-token')
  session.setItem('store_access_token', 'cognito-token')
  session.setItem('demo_csrf_token', 'csrf-token')
  local.setItem(CUSTOMER_TOKEN, 'legacy-token')

  clearCustomerToken(session, local)

  assert.equal(session.getItem(CUSTOMER_TOKEN), null)
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
  assert.equal(session.getItem('store_access_token'), 'cognito-token')
  assert.equal(session.getItem('demo_csrf_token'), 'csrf-token')
})

test('failed session storage writes remove the legacy JWT and fail closed', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  local.setItem(CUSTOMER_TOKEN, 'legacy-token')
  const failingSession = {
    getItem: session.getItem.bind(session),
    removeItem: session.removeItem.bind(session),
    setItem: () => { throw new Error('storage disabled') },
  }

  assert.equal(migrateLegacyCustomerToken(failingSession, local), null)
  assert.equal(session.getItem(CUSTOMER_TOKEN), null)
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
})

test('connection and reconnection reads use the latest session JWT', () => {
  const session = new MemoryStorage()
  session.setItem(CUSTOMER_TOKEN, 'first-token')
  assert.equal(readCustomerToken(session), 'first-token')

  session.setItem(CUSTOMER_TOKEN, 'second-token')
  assert.equal(readCustomerToken(session), 'second-token')
})

test('a demo authentication boundary clears the JWT and emits only non-secret metadata', () => {
  const session = new MemoryStorage()
  const local = new MemoryStorage()
  session.setItem(CUSTOMER_TOKEN, 'customer-secret-token')

  clearCustomerTokenForDemoBoundary('login', session, local)

  assert.equal(session.getItem(CUSTOMER_TOKEN), null)
  assert.equal(local.getItem(CUSTOMER_TOKEN), null)
  const boundaryEvent = local.getItem(CUSTOMER_DEMO_BOUNDARY_EVENT)
  assert.ok(boundaryEvent)
  assert.equal(boundaryEvent?.includes('customer-secret-token'), false)
  assert.equal(parseDemoBoundary(boundaryEvent), 'login')
  assert.equal(parseDemoBoundary('{"type":"logout"}'), 'logout')
  assert.equal(parseDemoBoundary('{"type":"expired"}'), 'expired')
  assert.equal(parseDemoBoundary('{"type":"unknown"}'), null)
})
