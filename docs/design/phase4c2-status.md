# AI Software Factory — Phase 4C-2: Execution Orchestration Flow

> 日期: 2026-08-05
> 前置: Phase 1-4C-1 (908 tests)
> 目标: 把已有模块连接成自动生产流水线 (Workflow→Assignment→Execution→Hermes→Result→Progress)

## 范围

- factory-core/orchestration/ (engine/pipeline/events)
- OrchestrationEngine: workflow started → step → requirement → Matcher → Allocator → Execution → Runner → Result → 推进
- Pipeline: execute_workflow(task_id) 完整链路; 失败 → Workflow FAILED (无半完成状态)
- 复用已有模块 (WorkflowEngine/AgentMatcher/AgentAllocator/ExecutionService/Runner/RuntimeAdapter), 禁止复制
- CLI: workflow run TASK_ID --auto
- Event: orchestration.started/step.started/step.completed/completed/failed
- 测试: 新增 ≥60, 908 不回归

## 禁止

修改 Hermes 核心 / Factory 逻辑入 Hermes / 新 Agent Runtime / LLM 编排 / Dashboard

## 约束

单进程 JSON persistence, Event Audit, 模块解耦; 无 Redis/MQ/ORM/Web/LLM SDK
