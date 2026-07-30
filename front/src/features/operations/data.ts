export type Tone = 'blue' | 'cyan' | 'violet' | 'green' | 'amber' | 'red' | 'slate'

export interface WorkflowRecord {
  id: string
  type: string
  asset: string
  applicant: string
  updatedAt: string
  status: string
  tone: Tone
}

export interface InventoryTask {
  id: string
  name: string
  scope: string
  owner: string
  deadline: string
  checked: number
  total: number
  exceptions: number
  status: string
  tone: Tone
}

export interface ApprovalRecord {
  id: string
  title: string
  applicant: string
  department: string
  submittedAt: string
  summary: string
  status: '待我审批' | '审批中' | '已通过' | '已拒绝'
  tone: Tone
}

export interface ImportJob {
  id: string
  fileName: string
  module: string
  operator: string
  createdAt: string
  total: number
  success: number
  failed: number
  status: string
  tone: Tone
}

export interface MasterDataGroup {
  key: string
  label: string
  description: string
  total: number
  active: number
  nodes: Array<{ code: string; name: string; detail: string; children?: number }>
}

export interface RoleRecord {
  key: string
  name: string
  description: string
  users: number
  permissions: number
  tone: Tone
}

export interface AuditLogRecord {
  id: string
  action: string
  module: string
  operator: string
  target: string
  time: string
  ip: string
  risk: '普通' | '关注' | '敏感'
  tone: Tone
}

export const workflowRecords: WorkflowRecord[] = [
  {
    id: 'LY202607240018',
    type: '资产领用',
    asset: 'MacBook Pro 14 · ZC20260083',
    applicant: '林小满',
    updatedAt: '今天 16:42',
    status: '待员工确认',
    tone: 'amber',
  },
  {
    id: 'DB202607240006',
    type: '资产调拨',
    asset: '戴尔显示器 · ZC20260116',
    applicant: '周明远',
    updatedAt: '今天 15:18',
    status: '审批中',
    tone: 'blue',
  },
  {
    id: 'WX202607230011',
    type: '维修处理',
    asset: 'ThinkPad X1 · ZC20250067',
    applicant: '资产运营组',
    updatedAt: '昨天 17:06',
    status: '维修中',
    tone: 'violet',
  },
  {
    id: 'TK202607230009',
    type: '资产退库',
    asset: 'iPhone 15 · ZC20250132',
    applicant: '陈思齐',
    updatedAt: '昨天 14:32',
    status: '待验收',
    tone: 'cyan',
  },
  {
    id: 'BF202607220003',
    type: '资产报废',
    asset: '联想台式机 · ZC20190128',
    applicant: '行政部',
    updatedAt: '07月22日 11:20',
    status: '待二级审批',
    tone: 'red',
  },
]

export const inventoryTasks: InventoryTask[] = [
  {
    id: 'PD20260701',
    name: '2026 年第三季度全员资产盘点',
    scope: '全公司 · 1,286 件资产',
    owner: '资产运营组',
    deadline: '2026-07-31 18:00',
    checked: 986,
    total: 1286,
    exceptions: 17,
    status: '进行中',
    tone: 'blue',
  },
  {
    id: 'PD20260608',
    name: '研发中心设备专项盘点',
    scope: '研发中心 · 346 件资产',
    owner: '赵一航、吴桐',
    deadline: '2026-07-28 18:00',
    checked: 302,
    total: 346,
    exceptions: 6,
    status: '进行中',
    tone: 'cyan',
  },
  {
    id: 'PD20260512',
    name: '上海办公室搬迁前盘点',
    scope: '上海办公室 · 228 件资产',
    owner: '何佳宁',
    deadline: '2026-07-20 18:00',
    checked: 228,
    total: 228,
    exceptions: 3,
    status: '待确认',
    tone: 'amber',
  },
]

export const approvalRecords: ApprovalRecord[] = [
  {
    id: 'SP202607240021',
    title: '资产调拨申请',
    applicant: '周明远',
    department: '产品设计部',
    submittedAt: '今天 15:18',
    summary: '将戴尔 U2723QE 显示器从北京总部调拨至上海办公室',
    status: '待我审批',
    tone: 'blue',
  },
  {
    id: 'SP202607240016',
    title: '资产报废申请',
    applicant: '彭雨欣',
    department: '行政部',
    submittedAt: '今天 11:26',
    summary: '3 台超过使用年限的办公电脑申请统一报废处置',
    status: '待我审批',
    tone: 'red',
  },
  {
    id: 'SP202607230027',
    title: '地点字典变更',
    applicant: '何佳宁',
    department: '资产运营组',
    submittedAt: '昨天 16:08',
    summary: '新增上海办公室 12F 直播间及两个设备存放区域',
    status: '审批中',
    tone: 'violet',
  },
  {
    id: 'SP202607220014',
    title: '资产转移申请',
    applicant: '陈思齐',
    department: '市场中心',
    submittedAt: '07月22日 10:35',
    summary: '员工部门调整后同步转移名下两件个人资产',
    status: '已通过',
    tone: 'green',
  },
]

export const importJobs: ImportJob[] = [
  {
    id: 'IMP20260724008',
    fileName: '第三季度新增资产.xlsx',
    module: '资产台账',
    operator: '资产管理员',
    createdAt: '今天 16:08',
    total: 128,
    success: 124,
    failed: 4,
    status: '部分成功',
    tone: 'amber',
  },
  {
    id: 'IMP20260723015',
    fileName: '上海办公室地点字典.xlsx',
    module: '地点字典',
    operator: '何佳宁',
    createdAt: '昨天 14:21',
    total: 38,
    success: 38,
    failed: 0,
    status: '导入成功',
    tone: 'green',
  },
  {
    id: 'EXP20260723009',
    fileName: '闲置资产清单_20260723.xlsx',
    module: '资产导出',
    operator: '资产管理员',
    createdAt: '昨天 10:12',
    total: 216,
    success: 216,
    failed: 0,
    status: '可下载',
    tone: 'blue',
  },
]

export const masterDataGroups: MasterDataGroup[] = [
  {
    key: 'company',
    label: '公司组织',
    description: '维护法人公司、事业群与部门层级',
    total: 46,
    active: 44,
    nodes: [
      { code: 'DS', name: '读书科技集团', detail: '集团总部', children: 5 },
      { code: 'DSBJ', name: '北京读书科技有限公司', detail: '北京 · 在用', children: 18 },
      { code: 'DSSH', name: '上海读书信息技术有限公司', detail: '上海 · 在用', children: 12 },
      { code: 'DSHZ', name: '杭州读书文化有限公司', detail: '杭州 · 在用', children: 8 },
    ],
  },
  {
    key: 'category',
    label: '资产分类',
    description: '统一资产分类、编码规则和使用年限',
    total: 36,
    active: 34,
    nodes: [
      { code: 'IT', name: '信息技术设备', detail: '默认使用年限 4 年', children: 12 },
      { code: 'OFFICE', name: '办公设备', detail: '默认使用年限 5 年', children: 8 },
      { code: 'MEDIA', name: '音视频设备', detail: '默认使用年限 4 年', children: 7 },
      { code: 'FURNITURE', name: '办公家具', detail: '默认使用年限 8 年', children: 9 },
    ],
  },
  {
    key: 'location',
    label: '地点字典',
    description: '维护城市、办公区、楼层和具体存放区域',
    total: 128,
    active: 124,
    nodes: [
      { code: 'BJ-HQ', name: '北京总部', detail: '北京市朝阳区', children: 48 },
      { code: 'SH-OFFICE', name: '上海办公室', detail: '上海市徐汇区', children: 36 },
      { code: 'HZ-OFFICE', name: '杭州办公室', detail: '杭州市滨江区', children: 29 },
      { code: 'WAREHOUSE', name: '资产仓库', detail: '跨城市仓储地点', children: 15 },
    ],
  },
  {
    key: 'public-user',
    label: '公共使用对象',
    description: '管理会议室、直播间和公共设备组',
    total: 24,
    active: 23,
    nodes: [
      { code: 'MEETING', name: '会议室设备', detail: '公共使用对象', children: 9 },
      { code: 'LIVE', name: '直播间设备', detail: '公共使用对象', children: 5 },
      { code: 'RECEPTION', name: '前台公共设备', detail: '公共使用对象', children: 4 },
      { code: 'MOBILE', name: '移动借用设备池', detail: '公共使用对象', children: 6 },
    ],
  },
  {
    key: 'supplier',
    label: '供应商',
    description: '沉淀采购、维修与处置合作方档案',
    total: 62,
    active: 57,
    nodes: [
      { code: 'SUP-001', name: '北京京东世纪贸易有限公司', detail: 'IT 设备 · 在用' },
      { code: 'SUP-008', name: '神州数码（中国）有限公司', detail: 'IT 设备 · 在用' },
      { code: 'SUP-016', name: '上海震旦办公自动化销售有限公司', detail: '办公设备 · 在用' },
      { code: 'SUP-027', name: '北京中科维保服务有限公司', detail: '维修服务 · 在用' },
    ],
  },
  {
    key: 'source',
    label: '资产来源',
    description: '维护采购、租赁、赠予等来源类型',
    total: 8,
    active: 8,
    nodes: [
      { code: 'PURCHASE', name: '采购', detail: '自有资产' },
      { code: 'LEASE', name: '租赁', detail: '租赁资产' },
      { code: 'TRANSFER', name: '公司间调入', detail: '内部调拨' },
      { code: 'GIFT', name: '赠予', detail: '其他来源' },
    ],
  },
]

export const roleRecords: RoleRecord[] = [
  {
    key: 'system-admin',
    name: '系统管理员',
    description: '拥有系统配置、角色权限与审计管理能力',
    users: 2,
    permissions: 48,
    tone: 'violet',
  },
  {
    key: 'asset-admin',
    name: '资产管理员',
    description: '管理授权范围内的资产、流程与盘点任务',
    users: 8,
    permissions: 31,
    tone: 'blue',
  },
  {
    key: 'inventory-admin',
    name: '盘点管理员',
    description: '创建盘点任务、处理异常并生成报告',
    users: 14,
    permissions: 12,
    tone: 'cyan',
  },
  {
    key: 'employee',
    name: '普通员工',
    description: '查看本人资产并完成领用、退库与自主盘点',
    users: 386,
    permissions: 7,
    tone: 'green',
  },
]

export const auditLogs: AuditLogRecord[] = [
  {
    id: 'LOG20260724164218',
    action: '创建领用单',
    module: '业务流程',
    operator: '资产管理员',
    target: 'LY202607240018',
    time: '今天 16:42:18',
    ip: '10.8.12.36',
    risk: '普通',
    tone: 'blue',
  },
  {
    id: 'LOG20260724160842',
    action: '批量导入资产',
    module: '导入导出',
    operator: '资产管理员',
    target: 'IMP20260724008 · 128 条',
    time: '今天 16:08:42',
    ip: '10.8.12.36',
    risk: '关注',
    tone: 'amber',
  },
  {
    id: 'LOG20260724152606',
    action: '审批通过',
    module: '审批中心',
    operator: '王北辰',
    target: 'SP202607240012',
    time: '今天 15:26:06',
    ip: '10.8.18.22',
    risk: '普通',
    tone: 'green',
  },
  {
    id: 'LOG20260724141033',
    action: '修改角色权限',
    module: '权限管理',
    operator: '超级管理员',
    target: '资产管理员 · 新增 supplier:edit',
    time: '今天 14:10:33',
    ip: '10.8.10.11',
    risk: '敏感',
    tone: 'red',
  },
  {
    id: 'LOG20260724112850',
    action: '资产状态变更',
    module: '资产台账',
    operator: '系统任务',
    target: 'ZC20250067 · 在用 → 维修中',
    time: '今天 11:28:50',
    ip: 'internal',
    risk: '普通',
    tone: 'violet',
  },
]
