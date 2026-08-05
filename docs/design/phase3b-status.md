# AI Software Factory — Phase 3B: Agent + Skill Registry

> 日期: 2026-08-05
> 前置: Phase 1 (ceb5f40) + Phase 2 (f4e96f3) + Phase 3A (b213a14, 223 tests)
> 目标: Agent 身份管理 + Skill 能力管理 + Registry 查询

## 范围

- factory-core/agents/ (models/registry/store/skills)
- Agent Model (AVAILABLE/WORKING/OFFLINE) + Skill Model (能力描述非执行)
- AgentRegistry + SkillRegistry (register/get/list/remove/find_by_skill)
- JSON 持久化 (.factory/agents/ + .factory/skills/)
- Event 集成 (agent.registered/updated/removed, skill.registered/removed)
- CLI: agent list/add, skill list/add
- 测试: 新增 ≥40, 223 不回归

## 不做 (Phase 4)

- Agent 自动调度 / Runtime / 通信 / Workflow Engine / Dashboard
- Task 自动分配 (owner 可引用 agent id, 不自动分配)

## 约束

- 不修改 Event/Task/Validation API / CLI 行为
- 无 Redis/MQ/ORM/Web/Dashboard/Agent Runtime
- 标准库 + pydantic, 单进程本地文件
