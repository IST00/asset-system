import assert from 'node:assert/strict'
import test from 'node:test'
import { formatAssetAmount, formatAssetDate } from './detailFormatters.ts'

test('formats a purchase date with the requested locale', () => {
  assert.equal(formatAssetDate('2026-07-12', 'en-US'), '07/12/2026')
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
  assert.equal(formatAssetAmount(14999, 'invalid_locale'), '¥14999.00')
})
