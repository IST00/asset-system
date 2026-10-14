import assert from 'node:assert/strict'
import test from 'node:test'
import { zhCNResources } from './zhCN.ts'

test('contains the required asset system navigation labels', () => {
  assert.equal(zhCNResources.app.name, '资产管理系统')
  assert.equal(zhCNResources.nav.home, '首页')
  assert.equal(zhCNResources.nav.assets, '资产台账')
  assert.equal(zhCNResources.nav.inventory, '资产盘点')
})

test('contains the asset usage ownership form labels', () => {
  assert.equal(zhCNResources.assets.form.labels.usage_company_name, '使用公司')
  assert.equal(zhCNResources.assets.form.labels.usage_department_name, '使用部门')
  assert.equal(zhCNResources.assets.form.labels.holder_user_name, '使用人')
})

test('contains the required dashboard section labels', () => {
  assert.equal(zhCNResources.dashboard.title, '资产仪表盘')
  assert.equal(zhCNResources.dashboard.sections.quickActions, '快捷操作')
  assert.equal(zhCNResources.dashboard.sections.pendingItems, '待办事项')
})
