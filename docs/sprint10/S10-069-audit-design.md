# S10-069 — Audit Intelligence 架构设计

> 日期:2026-08-17 | Sprint: S10-069 | 架构 (基于 GAP 分析 G1-G13)
> 原则: 统一 AuditEvent + 决策链重建 + 可解释 + 防篡改 + Context Budget
> 最高原则: Core + CLI + API + -h + Intent + Tests 同交付

---

## 1. 架构

```
各 Trace (planning/learning/debug/execution/cost/review)
              ↓ (Audit Adapter / 直接记录)
┌──────────────────────────────────────────────────┐
│ AuditStore (audit_store.py)                      │
│   append/get/query/get_chain/export              │
│   audit_events.json + event_hash + prev_hash     │
└─────────────────────┬────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│ AuditQuery → AuditDecisionChain → AuditExplain    │
│  (筛选/Top-K/ContextBudget/结构化"为什么")        │
└─────────────────────┬────────────────────────────┘
                      ↓
┌──────────────┬───────────────┬──────────────────┐
│ CLI (12 命令) │ API (10 端点)  │ Intent 关键词     │
└──────────────┴───────────────┴──────────────────┘
```

## 2. AuditEvent (audit_event.py)

```
@dataclass AuditEvent:
  audit_id (uuid4) / trace_id / correlation_id / project_id / workspace_id /
  task_id / agent_id / actor_type (user/system/agent/llm/tool) / actor_id /
  event_type (30+ 标准类型) / action / timestamp / lifecycle_state / source /
  input_reference / decision / decision_reason / evidence / policy /
  policy_result / approval / parent_event_id / related_event_ids /
  artifact_reference / cost_reference / memory_reference / debug_reference /
  result / impact / risk / status / metadata /
  event_hash / previous_event_hash

EventType (30+): PRODUCT_CREATED/DISCOVERY_COMPLETED/PRODUCT_INTELLIGENCE/
  PLAN_CREATED/PLAN_CHANGED/TASK_CREATED/TASK_ASSIGNED/AGENT_STARTED/
  AGENT_COMPLETED/LLM_CALL/TOOL_CALL/ARTIFACT_CREATED/TEST_STARTED/
  TEST_FAILED/TEST_PASSED/DEBUG_STARTED/ROOT_CAUSE_IDENTIFIED/
  DEBUG_STRATEGY_SELECTED/REPAIR_STARTED/REPAIR_COMPLETED/MEMORY_RETRIEVED/
  MEMORY_LEARNED/GOVERNANCE_CHECK/BUDGET_WARNING/BUDGET_BLOCKED/
  REVIEW_REQUESTED/REVIEW_APPROVED/REVIEW_REJECTED/TASK_BLOCKED/
  TASK_COMPLETED/DELIVERY_CREATED/USER_ACCEPTANCE/PROJECT_DELIVERED

脱敏: 键名黑名单 (api_key/secret/password/token/credential) 递归删除;
  原始 Prompt/Context 不落盘 (只存 input_reference/hash/summary)
hash: sha256(audit_id + canonical_json + previous_event_hash)
```

## 3. AuditStore (audit_store.py)

```
class AuditStore:
  append(event) -> AuditEvent (hash 链 + 落盘 audit_events.json)
  get(audit_id) / query(...) / get_chain(trace_id) / export() / stats()
  AuditStore 接口化: 未来可换 SQLite/PG/ES (当前 JSON)
```

## 4. AuditQuery (audit_query.py)

```
class AuditQuery:
  by_project(project_id) / by_task(task_id) / by_agent(agent_id) /
  by_trace(trace_id) / by_event_type(type) / by_actor(actor) /
  by_decision() / by_status() / by_risk() / by_time(start, end)
  → 筛选 + 排序 + 分页 + Top-K
```

## 5. AuditDecisionChain (audit_chain.py)

```
class AuditDecisionChain:
  get_chain(trace_id) -> dict:
    {root_event, children, related_events, final_outcome, chain: [事件序列]}
  build(trace_id) — 从 correlation_id/parent_event_id 重建决策链
```

## 6. AuditExplain (audit_explain.py)

```
class AuditExplain:
  why_created(task_id) / why_agent(agent_id) / why_stopped(project) /
  why_debug(debug_id) / why_cost(project) / who_approved(project)
  → {summary, evidence, decision, related_events, cost, policy, approval, outcome}
  默认结构化 (不调 LLM); 可选 LLM (ContextBudget 保护)
```

## 7. AuditContext (audit_context.py)

```
class AuditContextBudget:
  fit(events, max_tokens) -> (selected, stats)
  stats: candidates/selected/discarded/estimated_tokens/max_tokens/latency
```

## 8. AuditIntegrity (audit_integrity.py)

```
class AuditIntegrity:
  hash_event(event) -> str (sha256)
  verify_chain(events) -> bool (检测篡改: hash 链断裂)
```

## 9. CLI (session/actions.py + intent.py)

```
factory audit events     — "查看审计记录"/"审计记录"
factory audit trace      — "审计追踪"/"查看审计链路" (参数 trace_id)
factory audit chain      — "审计决策链" (参数 trace_id)
factory audit decision   — "审计决策"
factory audit explain    — "为什么创建这个任务"/"为什么选择这个Agent"/"为什么停了"
factory audit task       — "审计任务" (参数 task_id)
factory audit agent      — "审计Agent" (参数 agent_id)
factory audit cost       — "查看项目成本审计"/"成本审计"
factory audit export     — "导出审计"
factory audit stats      — "审计统计"
-h: 全注册 + intent 关键词
```

## 10. API (api/audit.py)

```
GET  /api/audit/events
GET  /api/audit/trace/{trace_id}
GET  /api/audit/chain/{trace_id}
GET  /api/audit/task/{task_id}
GET  /api/audit/agent/{agent_id}
GET  /api/audit/decisions
POST /api/audit/explain
GET  /api/audit/cost/{project_id}
GET  /api/audit/stats
POST /api/audit/export
CLI 与 API 同一 AuditStore/Core
```

## 11. 关联 (reference 不复制)

```
CostLedger → cost_reference (cost_records.json id)
ReviewGate → approval (reviewer/decision)
Memory → memory_reference (experience_id)
Debug → debug_reference (debug_id)
```

## 12. 测试计划 (120+)

```
Core (>=60): Event/Store/Query/Chain/Explain/ContextBudget/Redaction/Hash
CLI (>=15): 10+ 命令 + intent
API (>=20): 10 端点
Integration (>=20): 真实 E2E 5 场景 (A: 全链 / B: Debug / C: Governance / D: Cost / E: Security)
Security (>=10): 脱敏/hash/防篡改
```

## 13. 边界

- 不删除现有 Trace (Adapter 统一, 保留原 API)
- 不重实现 CostLedger/ReviewGate/Memory (reference 关联)
- 不引入完整 IAM (接口预留)
- 不引入 LLM 为默认 (结构化优先)

---

> 架构完毕 | AuditEvent + Store + Query + Chain + Explain + Integrity + CLI + API
