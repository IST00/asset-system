# 后端自动化覆盖率基线

> 这是风险定位基线，不是“达到百分比即可上线”的替代门禁。核心状态、金额、权限、并发、审计和恢复仍须按业务场景验收。

## 本次执行

| 字段 | 内容 |
| --- | --- |
| 日期 | 2026-08-11 |
| 候选提交 | `cf831166e9c458a8ef9c4fe38d92a48e0d203e68`；工作区有未提交改动 |
| Python | 3.12.11；不符合冻结要求 3.13，见 PILOT-001 |
| 命令 | `cd back && .venv/bin/python -m pytest tests --ignore=tests/test_environment_contract.py --cov=app --cov-report=term-missing --cov-report=json:/tmp/asset-system-coverage-after-management.json -q` |
| 用例结果 | `696 passed in 148.64s` |
| 语句覆盖 | 10,008 条；覆盖 8,896 条；未覆盖 1,112 条；总覆盖率 89% |
| 排除项 | `tests/test_environment_contract.py`，因锁文件和工具链已由 PILOT-001 单独阻断 |

完整质量门禁必须另行运行全部测试；排除环境契约只用于观察业务代码覆盖率，不能记录为全量 Pytest 通过。

## 风险排序

| 优先级 | 模块 | 覆盖率 | 判断 | 下一组测试 |
| --- | --- | ---: | --- | --- |
| 待复验 | `app/services/asset_management_service.py` | 85% | 新增 22 条定向用例，已覆盖正常执行、校验失败、跨组织、版本冲突、业务锁、事务回滚、审计和部分 HTTP 边界；审批入口缺陷独立见 PILOT-009 | 独立复验并补剩余引用资料、禁用用户、公共对象调拨和关系错误分支 |
| P1 | `app/services/inventory_service.py` | 75% | 685 条语句且状态分支密集，盘点异常处理和重开属于高风险核心流程 | 补发布/提交/确认/异常处置/结束/重开的非法转换、重复提交、并发和权限边界 |
| P1 | `app/services/import_service.py` | 79% | 547 条语句，导入会批量修改资产和基础数据 | 补解析错误聚合、确认幂等、部分失败原子性、重复文件、越权和大文件边界 |
| P2 | `app/observability/__init__.py` | 73% | 日志轮转、启动路径和非请求 trace 上下文未充分覆盖 | 补日志目录失败、轮转配置、敏感字段过滤、Celery/CLI trace 和异常请求 |
| P2 | `app/services/approval_service.py` | 21% | 应用和测试中无调用方，只有 `app.services` 导出；可能是被新审批内核替代的遗留实现 | 先做调用链评审；确认废弃后删除，确认保留则接入唯一审批入口并补状态竞争测试 |
| P1 | `app/tasks/__init__.py` | 0% | 只有示例任务，没有正式业务任务 | 与 PILOT-006 一起新增任务注册、幂等、重试、失败记录和 worker/beat 冒烟测试 |

## 基线规则

1. 当前总覆盖率回归线提升为 89%，新增代码不得通过删除测试或扩大排除范围维持数字。
2. 总覆盖率不掩盖核心模块低覆盖；PILOT-008 独立复验通过前，保留 `asset_management_service` 的定向覆盖率证据。
3. 不以逐行覆盖为目标。优先覆盖状态迁移、金额、权限、组织数据范围、乐观锁、幂等、并发、事务回滚和审计副作用。
4. 死代码不靠无意义测试提高数字；先确认调用关系，再删除或接入。
5. PILOT-001 修复后，用 Python 3.13 在干净安装环境重新生成本基线，并把 coverage JSON/HTML 报告保存到受控证据库。

临时覆盖率回归命令：

```bash
cd back
.venv/bin/python -m pytest tests \
  --cov=app \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-fail-under=89
```

该命令包含环境契约；在 PILOT-001 未修复前预期仍会失败，不能通过 `--ignore` 绕过正式质量门禁。
