# AI Software Factory — Phase 4B-3: Agent Assignment Layer

> 日期: 2026-08-05
> 前置: Phase 1-4B-2 (684 tests)
> 目标: Agent Matching + Assignment (ExecutionRequest 由哪个 Agent 执行)

## 范围

- factory-core/assignment/ (models/matcher/allocator/store)
- AgentAssignment (ASSIGNED/WORKING/COMPLETED/FAILED/RELEASED)
- AgentMatcher (role 匹配 + skill 包含 + AVAILABLE, 多候选按 skill 数排序)
- AgentAllocator (assign/release/complete, Agent 状态 WORKING↔AVAILABLE)
- Event 集成 (agent.assignment.* + agent.released)
- Execution 集成 (填充 agent_id, 不自动执行)
- CLI: agent assign/assignments/release
- 测试: 新增 ≥50, 684 不回归

## 原则

Agent != Assignment (Registry=员工信息, Assignment=工作关系, 不混写)

## 禁止

Agent Runtime 执行 / Hermes / LLM / 写码 / 改文件 / 多 Agent / Workflow 自动执行

## 约束

单进程本地 JSON, Event Audit, 可测试; 无 Redis/MQ/ORM/Web/LLM SDK
