# 角色、组织与数据范围权限矩阵

候选版本：________　模拟数据快照：________　执行人：________　执行时间：________

## 固定测试角色

| 角色标识 | 组织/范围 | 说明 |
| --- | --- | --- |
| `SUPER_ADMIN` | 全部模拟组织 | 系统管理和审计验证专用 |
| `ASSET_ADMIN_ORG_A` | `SIM-ORG-A` | Org A 资产管理 |
| `INVENTORY_ADMIN_ORG_A` | `SIM-ORG-A` | Org A 盘点管理 |
| `APPROVER_ORG_A` | `SIM-ORG-A` | Org A 审批节点 |
| `USER_ORG_A` | `SIM-ORG-A` | Org A 普通用户 |
| `USER_ORG_B` | `SIM-ORG-B` | 跨组织反向验证 |
| `DISABLED_USER` | `SIM-ORG-A` | 停用账号与旧会话验证 |

## 预期结果代码

- `ALLOW`：请求成功，返回数据仅在授权范围内，并产生应有审计。
- `DENY`：HTTP 401/403 或项目统一未认证/禁止结果；数据库零变化，且安全/拒绝审计符合系统约定。
- `FILTER`：请求成功，但 Org B、敏感金额或无权限字段不可见。
- `N/A`：角色职责不包含该操作，执行记录必须说明依据。

## 主矩阵

| 能力/目标 | SUPER_ADMIN | ASSET_ADMIN_ORG_A | INVENTORY_ADMIN_ORG_A | APPROVER_ORG_A | USER_ORG_A | USER_ORG_B | DISABLED_USER |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 查看 Org A 资产 | ALLOW | ALLOW | ALLOW | 按权限 FILTER | 本人相关 FILTER | DENY | DENY |
| 查看 Org B 资产 | ALLOW | DENY | DENY | DENY | DENY | 本人相关 FILTER | DENY |
| 新增/编辑 Org A 资产 | ALLOW | ALLOW | DENY | DENY | DENY | DENY | DENY |
| 批量维护 Org A/Org B 混合 ID | ALLOW | DENY（整批或逐条安全失败） | DENY | DENY | DENY | DENY | DENY |
| 查看资产金额 | ALLOW | 仅有金额权限时 ALLOW | FILTER | FILTER | FILTER | FILTER | DENY |
| 发起 Org A 领用/归还 | ALLOW | ALLOW | 按业务权限 | 按业务权限 | ALLOW（本人） | DENY | DENY |
| 审批 Org A 当前节点 | ALLOW | 仅被配置时 ALLOW | DENY | ALLOW | DENY | DENY | DENY |
| 审批 Org B 当前节点 | ALLOW | DENY | DENY | DENY | DENY | 按 Org B 配置 | DENY |
| 创建/发布 Org A 盘点 | ALLOW | 仅有盘点权限时 ALLOW | ALLOW | DENY | DENY | DENY | DENY |
| 提交本人 Org A 盘点结果 | ALLOW | ALLOW | ALLOW | 按任务范围 | ALLOW | DENY | DENY |
| 处理 Org A 盘点异常 | ALLOW | 仅有盘点管理权限时 ALLOW | ALLOW | DENY | DENY | DENY | DENY |
| 导出 Org A 资产 | ALLOW | 仅有导出权限时 ALLOW | DENY | DENY | DENY | DENY | DENY |
| 下载 Org A 附件 | ALLOW | ALLOW | 任务相关 FILTER | 业务相关 FILTER | 本人相关 FILTER | DENY | DENY |
| 猜测 Org B 附件 ID | ALLOW | DENY | DENY | DENY | DENY | 按自身范围 FILTER | DENY |
| 查看操作日志 | ALLOW | 仅授权范围 FILTER | DENY | DENY | DENY | DENY | DENY |
| 查看安全事件 | ALLOW | DENY | DENY | DENY | DENY | DENY | DENY |
| 管理用户/角色/权限 | ALLOW | DENY | DENY | DENY | DENY | DENY | DENY |
| 撤销其他会话 | ALLOW | 仅本人其他会话 | 仅本人其他会话 | 仅本人其他会话 | 仅本人其他会话 | 仅本人其他会话 | DENY |

## 绕过路径专项检查

| 完成 | 编号 | 操作 | 期望 | 结果 | 证据/缺陷 |
| --- | --- | --- | --- | --- | --- |
| [ ] | PERM-01 | 列表筛选参数改为 Org B | Org A 角色得不到 Org B 数据 | 未执行 | — |
| [ ] | PERM-02 | 直接访问已知 Org B 资源 ID | `DENY`，不区分“存在但无权”和“不存在”造成信息泄露 | 未执行 | — |
| [ ] | PERM-03 | 批量请求混入一个 Org B ID | 不得让混入项绕过逐条权限，事务结果符合接口约定 | 未执行 | — |
| [ ] | PERM-04 | 导出筛选条件指向 Org B | 文件中零 Org B 行，任务本身也不可越权下载 | 未执行 | — |
| [ ] | PERM-05 | 修改附件 ID/资产 ID 组合 | `DENY`，不返回文件名、大小或内容 | 未执行 | — |
| [ ] | PERM-06 | 撤销角色权限后重放旧 Token | 权限立即按服务端最新状态判断 | 未执行 | — |
| [ ] | PERM-07 | 停用用户重放旧 Token | `DENY`，无业务写入 | 未执行 | — |
| [ ] | PERM-08 | 并发撤权与写操作 | 不得在撤权后提交成功；结果有可追踪审计 | 未执行 | — |
| [ ] | PERM-09 | 修改前端隐藏字段或直接调用接口 | 后端独立校验，不能依赖前端按钮隐藏 | 未执行 | — |
| [ ] | PERM-10 | 审计接口尝试查询其他组织或敏感详情 | 仅超级管理员或明确授权范围可见，敏感值始终脱敏 | 未执行 | — |

## 阶段出口

- [ ] 每个 `DENY` 均确认数据库零变化；
- [ ] 列表、详情、批量、导出、附件和审计采用一致数据范围；
- [ ] 停用用户、被撤销会话和被撤销权限不能继续访问；
- [ ] 无跨组织数据泄漏或资源存在性侧信道；
- [ ] P0/P1 为零。
