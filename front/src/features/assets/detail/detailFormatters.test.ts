import assert from 'node:assert/strict'
import test from 'node:test'
import { formatAssetAmount, formatAssetDate, formatAssetDateTime } from './detailFormatters.ts'

test('formats a purchase date with the requested locale', () => {
  assert.equal(formatAssetDate('2026-07-12', 'en-US'), '07/12/2026')
})

test('formats a date time with the requested locale', () => {
  const value = '2026-07-12T09:20:00+08:00'
  const expected = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))

  assert.equal(formatAssetDateTime(value, 'en-US'), expected)
})

test('formats an amount with the requested locale', () => {
  const expected = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(14999)

  assert.equal(formatAssetAmount(14999, 'en-US'), expected)
})

test('falls back safely when Intl cannot use the locale', () => {
  assert.equal(formatAssetDate('2026-07-12', 'invalid_locale'), '2026-07-12')
  assert.equal(
    formatAssetDateTime('2026-07-12T09:20:00+08:00', 'invalid_locale'),
    '2026-07-12T09:20:00+08:00',
  )
  assert.equal(formatAssetAmount(14999, 'invalid_locale'), '¥14999.00')
})
