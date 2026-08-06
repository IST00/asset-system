import assert from 'node:assert/strict'
import test from 'node:test'
import {
  demoCredentials,
  demoPermissions,
  demoToken,
  demoUser,
  isDemoCredentials,
  isDemoLoginEnabled,
} from './demoAuth.ts'

test('enables demo login only for the explicit true value', () => {
  assert.equal(isDemoLoginEnabled('true'), true)
  assert.equal(isDemoLoginEnabled('false'), false)
  assert.equal(isDemoLoginEnabled(undefined), false)
})

test('provides a demo administrator that can experience the asset MVP', () => {
  assert.equal(demoToken.length > 0, true)
  assert.equal(demoUser.permissions?.includes('asset:view'), true)
  assert.equal(demoUser.permissions?.includes('asset:create'), true)
  assert.equal(demoUser.permissions?.includes('asset:amount:view'), true)
  assert.deepEqual(demoUser.permissions, [...demoPermissions])
})

test('accepts only the documented local demo account', () => {
  assert.equal(isDemoCredentials(demoCredentials), true)
  assert.equal(isDemoCredentials({ username: 'admin', password: 'wrong-password' }), false)
  assert.equal(isDemoCredentials({ username: 'other', password: 'admin123' }), false)
})
