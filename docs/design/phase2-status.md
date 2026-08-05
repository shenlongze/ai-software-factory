# AI Software Factory — Phase 2: Factory Control CLI

> 日期: 2026-08-05
> 前置: Phase 1 Event Logger MVP (ceb5f40, 69 tests)
> 目标: Control Plane — CLI 控制入口 (Dashboard 延后)

## 范围

- factory-core/tasks/: Task Model (Pydantic) + Task Store (JSON/YAML 文件持久化)
- factory-core/cli/: CLI (argparse/Typer, 不引重量级)
- 命令: init / task create / task list / task status / event logs / status / validate
- Event 集成: 所有 CLI 行为经 EventLogger 产生 Event

## 约束

- 不修改 docs 设计 / 已有 Event API
- 无 ORM/Redis/消息队列/Web Dashboard
- 单进程本地, SQLite EventStore
- Task 状态: BACKLOG/ARCHITECTURE/DEVELOPMENT/TESTING/DONE
- 不删已有测试

## 完成标准

pytest 全绿 (69 已有 + 新增 CLI/Task 测试), CLI 命令可用
