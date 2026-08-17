# S10-069 — GAP ANALYSIS

> 日期:2026-08-17 | Sprint: S10-069 | P0 现状审查
> 目标: 从"有很多 Trace"→"统一 Audit Intelligence, 可重建完整决策链"

---

## 16 问回答

### G1: 当前 Trace 是否有统一 trace_id / correlation_id?
```
❌ 无统一 correlation_id。
✅ 各 Trace 有自己的 id: planning_trace.trace_id (uuid4, 每次独立) / DebugSession.trace_id /
   DebugTrace / LearningTrace — 各自生成, 互不关联。
❌ 无 parent_execution_id 全链贯通 (planning_trace 有字段但 Debug/Memory 无)。
```

### G2: 能否把 Product→Plan→Task→Agent→...→Delivery 串起来?
```
❌ 不能。各 Trace 独立落盘 (planning_trace.json/learning_trace.json/debug_trace.json/
   execution_records.json/cost_records.json/review_records.json), 无统一事件流。
```

### G3: 能否回答"为什么"?
```
⚠️ 部分: DebugDecision.reason / ReplanDecision.reason / ReviewGate.reason 有原因文本,
   但分散, 无法统一查询"为什么这个决策"。
```

### G4: 能否回答"谁"?
```
⚠️ 部分: execution_records 有 agent; ReviewGate 有 reviewer; 无统一 actor (user/system/agent/LLM/tool)。
```

### G5: 能否回答"用了什么经验/知识"?
```
⚠️ 部分: DebugDecision.related_experiences 有; 无统一 memory_reference。
```

### G6: 能否回答"花了多少钱"?
```
✅ CostLedger (cost_records.json) 可回答 (total/by_agent/by_task/by_purpose), 但未与 Trace 事件关联。
```

### G7: 能否回答"谁批准了"?
```
✅ ReviewGate (reviewer 字段) 可回答, 但未统一到 Audit 视图。
```

### G8: 能否回答"Policy 为什么允许/阻止"?
```
⚠️ 部分: RepairSafety/Governance 有 reason; 无统一 policy_result 记录。
```

### G9: 能否回答"最终产生了什么影响"?
```
❌ 无统一 impact 字段 (artifact 变化/计划变化)。
```

### G10: Audit 是否可不在增加 LLM Context 下查询?
```
⚠️ 当前无 Audit 查询系统 — S10-069 必须设计 (查询→筛选→Top-K→ContextBudget→可选 LLM)。
```

### G11: 敏感信息/Secret 泄漏风险?
```
⚠️ planning_trace 有键白名单脱敏; 但 execution_records 直接存原始 error (可能含 key);
   AuditEvent 必须内置脱敏。
```

### G12: Audit 记录可否被普通业务流程修改/删除?
```
❌ 可 (execution_records 直接 append 覆写) — S10-069 需 event_hash/previous_hash 基础防篡改。
```

### G13: 能否导出一项目完整 Audit Report?
```
❌ 不能 (无统一存储)。
```

### G14: 能否只查询某 Task/Agent/Decision/Debug?
```
❌ 不能 (各 Trace 独立, 无统一查询)。
```

### G15: 能否对异常执行形成 Incident?
```
❌ 无 Incident 概念。
```

### G16: 能否支持未来企业 Audit/Compliance?
```
⚠️ 无 RBAC/Retention/Immutable 接口 — S10-069 数据模型须预留。
```

## GAP 汇总

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **AuditEvent 统一模型** | audit_id/trace_id/correlation_id/project/actor/event_type/action/timestamp/decision/policy/approval/result/impact + hash |
| G2 | **AuditStore** | append/get/query/get_chain/export (接口化, 可换 JSON/SQLite/PG) |
| G3 | **Trace Correlation** | 统一 correlation_id 贯通 Product→Delivery |
| G4 | **Decision Audit** | decision_type/alternatives/reason/evidence/confidence/policy/reviewer |
| G5 | **AuditDecisionChain** | get_chain(trace_id) → 根→子→相关→最终 |
| G6 | **AuditQuery** | project/task/agent/trace/event_type/actor/decision/status/risk/time 查询 |
| G7 | **AuditExplain** | 结构化回答"为什么" (默认不调 LLM, ContextBudget 保护) |
| G8 | **Cost/Governance/Review 关联** | reference 关联 CostLedger/ReviewGate/Policy |
| G9 | **Memory/Debug 关联** | memory_reference/debug_reference (不复制记录) |
| G10 | **ContextBudget** | Audit 查询不无限膨胀 (candidates/selected/discarded/tokens) |
| G11 | **脱敏** | API key/secret/password 不进入 Audit + 原始 Prompt 不落盘 |
| G12 | **Audit Integrity** | event_hash + previous_event_hash (tamper-evident 基础) |
| G13 | **CLI/API** | 12 CLI 命令 + 10 API 端点 + intent + -h |

## 可复用 ✅

```
PlanningTrace (S10-062): 白名单脱敏模式 / trace_id
LearningTrace (S10-067): learning_trace.json 审计模式
DebugTrace (S10-068): debug_trace.json 审计模式
CostLedger (S10-063): 成本关联 (reference 不重实现)
ReviewGate (S10-063): 审批关联
execution_records: 执行记录
actions 注册 + api/ 路由模式
```

## 架构方向

```
audit/ (新增):
  audit_event.py     — AuditEvent + EventType + 脱敏 + hash
  audit_store.py     — AuditStore (append/get/query/get_chain/export + AuditStore 接口)
  audit_query.py     — AuditQuery (筛选/排序/分页)
  audit_chain.py     — AuditDecisionChain (get_chain 重建决策链)
  audit_explain.py   — AuditExplain (结构化"为什么" + ContextBudget)
  audit_context.py   — ContextBudget (复用 debug 模式)
  audit_integrity.py — event_hash + previous_event_hash

CLI: factory audit events/trace/chain/decision/explain/task/agent/cost/export/stats
API: GET /api/audit/events, /trace/{id}, /chain/{id}, /task/{id}, /agent/{id},
     /decisions, /cost/{project}, /stats; POST /api/audit/explain, /export
```

## 测试计划 (120+)

```
Core (>=60): Event/Store/Query/Chain/Explain/ContextBudget/Redaction/Hash
CLI (>=15): 12 命令 + intent
API (>=20): 10 端点
Integration (>=20): 真实 E2E 5 场景 (A: 全链 / B: Debug / C: Governance / D: Cost / E: Security)
Security (>=10): 脱敏/hash/防篡改
```

## 不该现在做 🚫

```
完整企业 IAM/RBAC/SSO (接口预留)
区块链式存储 (event_hash 基础即可)
多后端 Audit Storage (接口化, 当前 JSON)
```

---

> GAP 完毕 | G1-G13 缺失 | 现有 Trace 可适配 | 统一 Audit Intelligence
