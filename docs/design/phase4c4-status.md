# AI Software Factory — Phase 4C-4: Dashboard MVP

> 日期: 2026-08-06
> 前置: Phase 1-4C-3 (1103 tests)
> 目标: CLI 可视化控制台 (Rich, 非 Web)

## 范围

- factory-core/dashboard/ (models/collector/renderer/views)
- FactorySnapshot (tasks/agents/workflows/executions/checkpoints/metrics)
- DashboardCollector (读全部 store → Snapshot)
- DashboardRenderer (Rich: Overview/Tasks/Agents/Workflows/Executions/Recovery)
- CLI: factory dashboard
- Metrics (success rate/failure count/validation summary)
- Event: dashboard.viewed
- 测试: 新增 ≥50, 1103 不回归

## 原则

只读 (不能修改任何状态), 模块解耦, Event Audit

## 技术

Python + Rich (允许); 禁止 React/Vue/FastAPI/Web Server/数据库
