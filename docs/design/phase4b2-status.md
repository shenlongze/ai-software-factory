# AI Software Factory — Phase 4B-2: Execution Dispatch Layer

> 日期: 2026-08-05
> 前置: Phase 1-4B-1 (584 tests)
> 目标: ExecutionRequest → Runtime Adapter 的执行控制层

## 范围

- factory-core/execution/ (runner/dispatcher/service)
- ExecutionDispatcher (resolve runtime → Adapter → execute)
- ExecutionRunner (PENDING → started → execute → SUCCESS/FAILED → completed/failed)
- Result 持久化 (复用 Runtime Store, 不新增数据库)
- EchoRuntimeAdapter (测试用 mock, 验证链路)
- Workflow 联动 (step → request → runner → result; 成功 step.completed / 失败 workflow.failed)
- CLI: execution run/status
- 测试: 新增 ≥50, 584 不回归

## 禁止

真实 Hermes / LLM / 自动写码 / 改文件 / 自动 Agent 调度 / 多 Agent

## 约束

- 单进程 JSON persistence, Event audit, 可替换 Runtime
- 无 Redis/MQ/ORM/Web/LLM SDK
- Agent 边界: 支持 agent_id 但不自动选择 (Scheduler 后续)
