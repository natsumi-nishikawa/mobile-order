import assert from 'node:assert/strict'
import test from 'node:test'

import { safeStoreReturnPath } from '../src/storeRedirect.ts'


test('allows internal staff and admin paths', () => {
  assert.equal(safeStoreReturnPath('/staff'), '/staff')
  assert.equal(safeStoreReturnPath('/staff/orders'), '/staff/orders')
  assert.equal(safeStoreReturnPath('/staff/accounting/123'), '/staff/accounting/123')
  assert.equal(safeStoreReturnPath('/admin'), '/admin')
  assert.equal(safeStoreReturnPath('/admin/accounting/123'), '/admin/accounting/123')
})

test('rejects absolute and scheme-relative URLs', () => {
  assert.equal(safeStoreReturnPath('https://evil.example'), '/staff')
  assert.equal(safeStoreReturnPath('http://evil.example'), '/staff')
  assert.equal(safeStoreReturnPath('//evil.example'), '/staff')
})

test('rejects backslash and encoded bypasses', () => {
  assert.equal(safeStoreReturnPath('/\\evil.example'), '/staff')
  assert.equal(safeStoreReturnPath('\\\\evil.example'), '/staff')
  assert.equal(safeStoreReturnPath('%2F%2Fevil.example'), '/staff')
  assert.equal(safeStoreReturnPath('https%3A%2F%2Fevil.example'), '/staff')
  assert.equal(safeStoreReturnPath('/staff%2F..%2Fadmin'), '/staff')
})

test('rejects empty, malformed and unsupported paths', () => {
  for (const value of [null, undefined, '', ' ', '/', '/customer', '/administrator', '/staff/unknown', '/admin/unknown', '/staff?next=//evil.example', '/admin#evil']) {
    assert.equal(safeStoreReturnPath(value), '/staff')
  }
})

test('enforces the authenticated Cognito group', () => {
  assert.equal(safeStoreReturnPath('/admin/products', ['staff']), '/staff')
  assert.equal(safeStoreReturnPath('/staff/orders', ['staff']), '/staff/orders')
  assert.equal(safeStoreReturnPath('/admin/products', ['admin']), '/admin/products')
  assert.equal(safeStoreReturnPath('/staff/orders', ['admin']), '/staff/orders')
  assert.equal(safeStoreReturnPath('https://evil.example', ['admin']), '/admin')
})
