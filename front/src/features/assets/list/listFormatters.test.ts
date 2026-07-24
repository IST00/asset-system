import assert from 'node:assert/strict'
import test from 'node:test'
import { formatAssetAmount, formatAssetDate } from './listFormatters.ts'

test('formats asset dates and CNY amounts with the active locale', () => {
  const zhDate = formatAssetDate('2026-07-12', 'zh-CN')
  const enDate = formatAssetDate('2026-07-12', 'en-US')
  const amount = formatAssetAmount(12345.6, 'zh-CN')

  assert.match(zhDate, /^2026/)
  assert.match(enDate, /2026$/)
  assert.match(amount, /12,345\.60/)
})

test('falls back safely when Intl formatting is unavailable', () => {
  assert.equal(formatAssetDate('2026-07-12', 'zh-CN', null), '2026-07-12')
  assert.equal(formatAssetDate('not-a-date', 'zh-CN'), 'not-a-date')
  assert.equal(formatAssetAmount(12345.6, 'zh-CN', null), '¥12,345.60')
})
