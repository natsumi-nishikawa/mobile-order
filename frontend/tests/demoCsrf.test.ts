import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DEMO_CSRF_KEY,
  clearDemoCsrfToken,
  readDemoCsrfToken,
  requireDemoCsrfToken,
  saveDemoCsrfToken,
} from '../src/demoCsrf.ts'

class MemoryStorage {
  private values = new Map<string, string>()

  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

test('uses an existing CSRF token without an unnecessary session request', async () => {
  const storage = new MemoryStorage()
  saveDemoCsrfToken('current-csrf', storage)
  let restoreCalls = 0

  const token = await requireDemoCsrfToken(async () => { restoreCalls += 1; return true }, storage)

  assert.equal(token, 'current-csrf')
  assert.equal(restoreCalls, 0)
})

test('restores a missing CSRF token before an unsafe request', async () => {
  const storage = new MemoryStorage()
  const token = await requireDemoCsrfToken(async () => {
    saveDemoCsrfToken('restored-csrf', storage)
    return true
  }, storage)

  assert.equal(token, 'restored-csrf')
})

test('does not allow an unsafe request when CSRF restoration fails', async () => {
  const storage = new MemoryStorage()
  let requestSent = false

  await assert.rejects(async () => {
    await requireDemoCsrfToken(async () => false, storage)
    requestSent = true
  }, /再ログイン/)

  assert.equal(requestSent, false)
  assert.equal(readDemoCsrfToken(storage), null)
})

test('clears a stale tab-local CSRF token at a demo boundary', () => {
  const storage = new MemoryStorage()
  storage.setItem(DEMO_CSRF_KEY, 'stale-csrf')
  clearDemoCsrfToken(storage)
  assert.equal(readDemoCsrfToken(storage), null)
})
