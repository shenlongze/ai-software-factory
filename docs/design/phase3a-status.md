# AI Software Factory — Phase 3A: Validation Engine

> 日期: 2026-08-05
> 前置: Phase 1 (ceb5f40) + Phase 2 (f4e96f3, 141 tests)
> 目标: factory validate 从 placeholder 升级为真实 Validation Engine

## 范围

- factory-core/validation/ (models.py / engine.py / rules.py / reports.py)
- 三层验证: L1 Factory / L2 Workflow / L3 Artifact Hook
- Event 集成: validation.started → rule.started → rule.completed → completed/failed
- CLI: factory validate TASK_ID 不变, 输出升级为 Validation Report
- 测试: 新增 ≥30, 已有 141 继续通过

## 不做 (后续 Phase)

- Agent Registry / Skill Registry / Dashboard / Task Recovery

## 约束

- 不修改 EventStore/EventLogger/TaskStore API / CLI 使用方式
- 无新数据库/ORM/Redis/MQ/Web/外部 API
- 单进程本地文件持久化
- 所有验证行为经 EventLogger, 不绕过
