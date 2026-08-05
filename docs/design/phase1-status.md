# AI Software Factory — Phase 1: Observation Layer MVP

> 日期: 2026-08-05
> 目标: Event Logger (Event = 唯一事实来源)
> 依据: docs/design/phase1-plan.md + docs/design/event-model.md
> 环境: .venv (python3.12 + pydantic 2.13 + pytest 9.1)

## 范围

1. Event Domain Model (Pydantic, 不可变, event_id/timestamp/project/task/agent/stage/action/result/evidence)
2. SQLite Event Store (sqlite3 标准库, append/query/by task/agent/project)
3. 六类 Event (task/agent/workflow/tool/validation/memory)
4. Metrics Query (聚合: task 数/agent 次数/success-failure/validation)
5. CLI 预留接口 (未来 factory logs/status)
6. pytest ≥25

## 工程规则

- 不修改 docs 架构设计
- 设计问题 → 记录 ADR (docs/adr/)
- 不提前实现 Dashboard
- 不引入复杂依赖 (仅 pydantic, 标准库 sqlite3)
- 单进程

## 完成标准

创建 Event → 写入 SQLite → 查询 → 生成指标 + pytest 全绿
