import assert from 'node:assert/strict'
import test from 'node:test'
import { beijingDateKey, formatBeijingDateTime, parseUtcInstant } from './dateTime.ts'

test('formats a UTC instant as Beijing time', () => {
  assert.equal(formatBeijingDateTime('2026-08-10T00:00:00Z'), '2026-08-10 08:00:00')
})

test('treats a legacy naive API datetime as UTC', () => {
  assert.equal(parseUtcInstant('2026-08-10T00:00:00').toISOString(), '2026-08-10T00:00:00.000Z')
})

test('computes the calendar date in Asia Shanghai', () => {
  assert.equal(beijingDateKey('2026-08-09T16:30:00Z'), '2026-08-10')
})

test('keeps an invalid API value visible for diagnosis', () => {
  assert.equal(formatBeijingDateTime('invalid-time'), 'invalid-time')
})
