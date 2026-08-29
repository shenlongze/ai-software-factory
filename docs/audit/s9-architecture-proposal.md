# S9 Architecture Proposal — Expert Assembly / Agent Kernel + HandoffBus

> 日期: 2026-08-29 | HEAD: 605d4a9b (v1.1.314) | 状态: PROPOSAL (实现前)

## 1. Existing Agent Capabilities (审计结果)
- **AgentEntity** (session/agent_entity.py): 完整 domain entity (agent_id/role/industry/capabilities/skills + 校验) — REAL
- **AgentRegistry** (session/agent_registry.py): add/get/list/remove + agents.json 持久化 — REAL
- **HandoffBus** (session/handoff_bus.py): HandoffMessage/HandoffResult/send/route + ArtifactRecord — REAL
- **ProjectSpine** (session/handoff.py): 交接卡 (progress/next_steps) — REAL (会话级)

## 2. Existing Abstractions
- Production Kernel (S1-S8): Artifact/NodeRun/ProductionRun/Verification/Repair/Recovery — REAL
- LLM Router (llm_gateway + config provider) — REAL (可复用)
- external_executor (codex/claude/hermes subprocess) — REAL

## 3. Gap Analysis
| 能力 | 现状 | S9 缺口 |
|------|------|---------|
| Agent Definition | REAL (AgentEntity) | 无 |
| Agent Registry | REAL | 无 |
| HandoffBus | REAL (消息级) | Artifact-centric 集成 |
| **AgentRun** | **MISSING** | 执行事实 + 状态机 |
| Agent → ProductionRun | **MISSING** | 集成层 |
| Agent Loop | **MISSING** | 专业角色循环 |
| CLI/API | **MISSING** | agent run/status + 端点 |
| 真实 Agent E2E | **MISSING** | Developer Agent 真实执行 |

## 4-6. Domain Model (新增)
- Agent = 专业员工定义 (复用 AgentEntity)
- AgentRun = 一次工作事实 (agent_run_id/agent_id/production_run_id/state/input_refs/output_refs/history) — **复用 ProductionRun 做底座**
- Handoff = Artifact-centric 传递 (from_agent_run/to_agent/input_artifacts/context_refs)

## 7-11. 关系决策
- Agent → AgentRun → **ProductionRun** (不新建第二套执行: AgentRun 包 ProductionRun)
- Agent → NodeRun: 经 executor_factory (Agent 不直接 subprocess)
- Agent → Artifact: ProductionRun 产出
- Agent → Verification: NodeRun verification (S5)
- Agent → Recovery: 复用 S7 (AgentRun 崩溃 = ProductionRun 恢复)

## 12. Persistence
```
agents/definitions/<agent_id>.json (复用 AgentRegistry)
agents/runs/<agent_run_id>.json (AgentRun 事实)
workflows/runs/<prun_id>.json (ProductionRun 底座)
```

## 13. CLI/API
```
factory agent list/show/run/status/history
factory handoff list/show
GET /api/agents, /api/agent-runs, /api/handoffs + POST /api/agent-runs
```

## 14. Audit
AGENT_RUN_CREATED/STARTED/COMPLETED/FAILED + HANDOFF_CREATED/ACCEPTED (EVENT_TYPES 注册)

## 15. Legacy Conflicts
- session/agent_loop.py 是会话聊天 Agent — 与生产 Agent 分离 (BYPASS, 不混用)
- 旧 workflow_runner — BYPASS (既有决策)

## 16. Migration
新 Agent Kernel 独立命名空间 (agent_kernel.py), 不破坏既有。

## 17. Test Strategy
24 项测试 (Definition/Run/Contract/Handoff/No-Hidden-State/Integration/Real E2E/Failure/Recovery)

## 18. Scope
Agent Kernel + 1 个真实 Developer Agent + 1 个真实 Handoff (Developer→QA)。不做 PM/Architect 等全角色。

---
## 实现计划 (最小增量)
1. agent_kernel.py: AgentRun 状态机 + AgentService (run/status/history) + Handoff 集成
2. CLI + API (同一 Service)
3. 测试 (24 项)
4. 真实 E2E: Developer Agent → 真实 executor → Artifact → Verification → Handoff → QA
