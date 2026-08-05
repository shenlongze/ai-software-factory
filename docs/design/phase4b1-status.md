# AI Software Factory — Phase 4B-1: Runtime Adapter Interface

> 日期: 2026-08-05
> 前置: Phase 1-4A (449 tests)
> 目标: Workflow Engine 与具体 Agent Runtime 之间的隔离层

## 范围

- factory-core/runtime/ (models/adapter/registry/store)
- ExecutionRequest/ExecutionResult (PENDING/RUNNING/SUCCESS/FAILED)
- RuntimeAdapter 抽象接口 (execute, 无具体实现)
- RuntimeRegistry (register/get/list/remove, AVAILABLE/DISABLED)
- JSON 持久化 (.factory/runtimes/runtimes.json)
- Event 集成 (runtime.* + execution.* 经 EventLogger)
- WorkflowEngine.execute_step (创建 execution, 不自动调用 Runtime)
- CLI: runtime list/add, execution list
- 测试: 新增 ≥40, 449 不回归

## 禁止 (后续 Phase)

Hermes/LLM 调用 / 自动写码 / 改项目文件 / Agent 调度 / Skill 匹配 / 多 Agent / Dashboard

## 约束

- 单进程本地, 可测试可替换
- 无 Redis/MQ/ORM/Web/LLM SDK/外部 API
- 架构变化 → ADR
