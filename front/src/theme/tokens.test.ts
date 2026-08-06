import assert from 'node:assert/strict'
import test from 'node:test'
import { designTokens } from './tokens.ts'

test('defines one semantic palette for application surfaces', () => {
  assert.equal(designTokens.color.brand, '#2563eb')
  assert.equal(designTokens.color.canvas, '#f5f7fb')
  assert.equal(designTokens.color.surface, '#ffffff')
  assert.notEqual(designTokens.color.success, designTokens.color.danger)
  assert.match(designTokens.glass.surface, /^rgba\(/)
  assert.ok(designTokens.glass.blur >= 20)
})

test('keeps shared layout dimensions in centralized tokens', () => {
  assert.equal(designTokens.layout.railWidth, 72)
  assert.equal(designTokens.layout.mobileBreakpoint, 768)
  assert.ok(designTokens.layout.maxContentWidth >= 1200)
})
