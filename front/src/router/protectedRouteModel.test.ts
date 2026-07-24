import assert from 'node:assert/strict'
import test from 'node:test'
import { canAccessProtectedRoute } from './protectedRouteModel.ts'

test('requires a token even when legacy development bypass flags are supplied', () => {
  assert.equal(canAccessProtectedRoute('token'), true)
  assert.equal(Reflect.apply(canAccessProtectedRoute, undefined, [null, true, true]), false)
  assert.equal(canAccessProtectedRoute(null), false)
})
