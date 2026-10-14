/**
 * Shared display mappings for backend persisted enum codes.
 *
 * Keep these labels user-facing; unknown codes retain their value after a
 * readable prefix so support staff can still search logs and statuses.
 */
type LabelMap = Record<string, string>

function label(map: LabelMap, value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  return map[value] ?? `${fallback}（${value}）`
}

const assetStatusLabels: LabelMap = {
  IDLE: '闲置',
  PENDING_RECEIPT: '待接收',
  IN_USE: '在用',
  REPAIRING: '维修中',
  SCRAPPED: '已报废',
}

const approvalStatusLabels: LabelMap = {
  DRAFT: '草稿',
  PENDING: '待审批',
  WAITING: '等待前序审批',
  APPROVED: '已通过',
  REJECTED: '已拒绝',
  WITHDRAWN: '已撤回',
}

const executionStatusLabels: LabelMap = {
  NOT_STARTED: '待执行',
  PROCESSING: '执行中',
  SUCCESS: '已完成',
  FAILED: '执行失败',
  TERMINATED: '已终止',
}

const workflowStatusLabels: LabelMap = {
  PENDING_APPROVAL: '待审批',
  PENDING_ISSUE: '待管理员发放',
  PENDING_SIGN: '待员工签收',
  SIGN_REFUSED: '员工拒绝签收',
  PENDING_HANDOVER: '待交还',
  PENDING_INSPECTION: '待验收',
  RETURN_PROCESSING: '退库处理中',
  PROCESSING: '执行中',
  COMPLETED: '已完成',
  REJECTED: '已拒绝',
  WITHDRAWN: '已撤回',
  FAILED: '执行失败',
  TERMINATED: '已终止',
}

const workflowHandlerRoleLabels: LabelMap = {
  APPROVER: '审批人',
  ADMIN: '管理员',
  EMPLOYEE: '员工',
}

const operationTypeLabels: LabelMap = {
  STOCK_IN: '资产入账',
  PERSONAL_USE: '个人领用',
  PUBLIC_USE: '公共领用',
  PERSONAL_RETURN: '个人退库',
  PUBLIC_RETURN: '公共退库',
  TRANSFER: '资产交接',
  SCRAP: '资产报废',
  REPAIR_START: '发起维修',
  REPAIR_COMPLETE: '维修完成',
  PHYSICAL_INFO_CHANGE: '实物信息变更',
  FINANCIAL_INFO_CHANGE: '财务信息变更',
  WARRANTY_INFO_CHANGE: '保修信息变更',
}

const roleCodeLabels: LabelMap = {
  SUPER_ADMIN: '超级管理员',
  ASSET_ADMIN: '资产管理员',
  USER: '普通员工',
  EMPLOYEE: '普通员工',
}

const dataScopeLabels: LabelMap = {
  ALL: '全部组织',
  DEPARTMENT: '当前组织',
  DEPARTMENT_TREE: '当前及下级组织',
  CUSTOM: '自定义组织范围',
  SELF: '仅本人数据',
}

const inventoryVersionActionLabels: LabelMap = {
  SUBMIT: '提交盘点',
  ADMIN_MARK: '管理员标记',
  RESOLVE: '异常处理',
  RETURN: '退回修改',
  REOPEN: '重新开启',
  WITHDRAW: '撤回提交',
  END_COLLECTION: '结束收集',
  RESPONSIBILITY_TRANSFER: '转交责任人',
}

const securityEventLabels: LabelMap = {
  LOGIN_SUCCESS: '登录成功',
  LOGIN_FAILURE: '登录失败',
  LOGIN_BLOCKED: '登录被阻止',
  ACCOUNT_LOCKED: '账号锁定',
  ACCOUNT_UNLOCKED: '账号解锁',
  PASSWORD_CHANGED: '密码修改',
  PASSWORD_RESET: '重置密码',
  SESSION_REVOKED: '会话撤销',
  RATE_LIMITED: '触发限流',
  APPROVAL_STATUS_CHANGED: '审批状态变更',
  TRANSFER: '审批转交',
  REMIND: '审批催办',
}

const auditActionLabels: LabelMap = {
  STOCK_IN: '资产入账',
  ASSET_EDIT: '编辑资产',
  ASSET_BATCH_EDIT: '批量编辑资产',
  ASSET_ATTACHMENT_UPLOAD: '上传资产附件',
  ASSET_ATTACHMENT_VOID: '作废资产附件',
  ASSET_ATTACHMENT_COVER_UPDATE: '更新附件封面',
  ASSET_RELATION_ATTACH: '挂接附属资产',
  ASSET_RELATION_DETACH: '解除主附关系',
  ASSET_EXPORT_EXPIRE: '导出文件过期',
  ASSET_LABEL_PRINT: '打印资产标签',
  ASSET_DATA_COMPLETE: '资产资料补录',
  ASSET_USAGE_REVIEW_AND_ISSUE: '审批并发放资产',
  ASSET_USAGE_SIGN: '员工签收',
  ASSET_USAGE_SIGN_REFUSED: '员工拒收',
  ASSET_BORROW_EXTENSION_REQUESTED: '发起借用延期',
  ASSET_BORROW_EXTENSION_APPROVED: '批准借用延期',
  ASSET_BORROW_RETURN_REQUESTED: '发起归还',
  ASSET_RETURN_HANDED_OVER: '员工交还资产',
  ASSET_TRANSFER_HANDOVER_CREATED: '创建资产交接',
  ASSET_TRANSFER_OUTGOING_CONFIRMED: '确认转出',
  ASSET_TRANSFER_RECEIVED_CONFIRMED: '确认接收',
  ASSET_TRANSFER_REJECTED: '拒绝交接',
  IMPORT_PREVIEW: '导入预览',
  IMPORT_CONFIRM: '确认导入',
  PASSWORD_UPDATE: '修改密码',
  ROLE_CREATE: '新建角色',
  ROLE_UPDATE: '更新角色',
  ROLE_DELETE: '删除角色',
  ROLE_PERMISSIONS_UPDATE: '更新角色权限',
  USER_ROLES_UPDATE: '调整用户角色',
  INVENTORY_TASK_CREATE: '创建盘点任务',
  INVENTORY_TASK_PUBLISH: '发布盘点任务',
  INVENTORY_TASK_COMPLETE: '完成盘点任务',
  INVENTORY_TASK_CANCEL: '取消盘点任务',
  INVENTORY_COLLECTION_END: '结束盘点收集',
  INVENTORY_ITEM_SUBMIT: '提交盘点结果',
  INVENTORY_ADMIN_MARK: '管理员标记盘点',
  INVENTORY_ITEM_RETURN: '退回盘点明细',
  INVENTORY_ITEM_WITHDRAW: '撤回盘点明细',
  INVENTORY_ITEMS_REOPEN: '重开盘点明细',
  INVENTORY_EXCEPTION_RESOLVE: '处理盘点异常',
  INVENTORY_SURPLUS_RESOLVE: '处理盘盈',
  INVENTORY_RESPONSIBILITY_TRANSFER: '转交盘点责任',
  INVENTORY_ADMINS_UPDATE: '更新盘点管理员',
  INVENTORY_DEADLINE_UPDATE: '更新盘点截止时间',
  INVENTORY_REMINDER_SEND: '发送盘点催办',
  INVENTORY_REPORT_EXPORT: '导出盘点报告',
  APPROVAL_REQUEST_REMIND: '催办审批',
  APPROVAL_REQUEST_RESUBMIT: '重新提交审批',
  APPROVAL_REQUEST_WITHDRAW: '撤回审批申请',
  APPROVAL_TASK_TRANSFER: '转交审批任务',
  APPROVAL_FLOW_PUBLISH: '发布审批流程',
  APPROVAL_FLOW_ENABLE: '启用审批流程',
  APPROVAL_FLOW_DISABLE: '停用审批流程',
  PUBLIC_OBJECT_CREATE: '新建公共使用对象',
  PUBLIC_OBJECT_UPDATE: '更新公共使用对象',
  SUPPLIER_CREATE: '新建供应商',
  SUPPLIER_UPDATE: '更新供应商',
  SUPPLIER_ENABLE: '启用供应商',
  SUPPLIER_DISABLE: '停用供应商',
  SUPPLIER_DELETE: '删除供应商',
  LOCATION_DELETE: '删除存放地点',
  ASSET_CATEGORY_DELETE: '删除资产分类',
}

const auditResourceTypeLabels: LabelMap = {
  approval_flow_definition: '审批流程定义',
  approval_flow_version: '审批流程版本',
  approval_task: '审批任务',
  asset: '资产',
  asset_attachment: '资产附件',
  asset_borrow_extension_request: '借用延期申请',
  asset_category: '资产分类',
  asset_data_completion_batch: '资料补录批次',
  asset_lifecycle: '资产履历',
  asset_location: '存放地点',
  asset_relation: '主附资产关系',
  asset_return_request: '资产退库申请',
  asset_transfer_handover: '资产交接单',
  asset_usage_request: '资产领退申请',
  export: '导出',
  export_job: '导出任务',
  import_job: '导入任务',
  inventory_item: '盘点明细',
  inventory_scan_event: '盘点扫码事件',
  inventory_task: '盘点任务',
  operation_request: '业务申请',
  public_usage_object: '公共使用对象',
  role: '角色',
  supplier: '供应商',
  user: '用户',
}

const scrapDispositionLabels: LabelMap = {
  SCRAP: '报废处置',
  DETACH: '拆解处置',
  BLOCK: '阻断处置',
}

export function assetStatusLabel(value?: string | null): string {
  return label(assetStatusLabels, value, '未知状态')
}

export function approvalStatusLabel(value?: string | null): string {
  return label(approvalStatusLabels, value, '未知审批状态')
}

export function executionStatusLabel(value?: string | null): string {
  return label(executionStatusLabels, value, '未知执行状态')
}

export function workflowStatusLabel(value?: string | null): string {
  return label(workflowStatusLabels, value, '未知状态')
}

export function workflowHandlerRoleLabel(value?: string | null): string {
  return label(workflowHandlerRoleLabels, value, '未知处理角色')
}

export function operationTypeLabel(value?: string | null): string {
  return label(operationTypeLabels, value, '未知业务类型')
}

export function roleCodeLabel(value?: string | null): string {
  return label(roleCodeLabels, value, '未知角色')
}

export function dataScopeLabel(value?: string | null): string {
  return label(dataScopeLabels, value, '其他数据范围')
}

export function inventoryVersionActionLabel(value?: string | null): string {
  return label(inventoryVersionActionLabels, value, '未知盘点操作')
}

export function securityEventLabel(value?: string | null): string {
  return label(securityEventLabels, value, '未知安全事件')
}

export function auditActionLabel(value?: string | null): string {
  return label(auditActionLabels, value, '未知操作')
}

export function auditResourceTypeLabel(value?: string | null): string {
  return label(auditResourceTypeLabels, value, '未知资源')
}

export function scrapDispositionLabel(value?: string | null): string {
  return label(scrapDispositionLabels, value, '未知处置方式')
}
