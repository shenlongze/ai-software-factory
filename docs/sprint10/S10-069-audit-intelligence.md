# S10-069 — Audit Intelligence (Enterprise Audit, Decision Trace & Explainability)

> 日期:2026-08-17 | Sprint: S10-069 | Audit Intelligence
> 状态: 从"有很多 Trace"→"统一 Audit Intelligence, 可重建完整决策链"

---

## 1. 核心能力

```
统一 AuditEvent (33 EventType + trace/correlation + actor + decision + policy +
  approval + references + event_hash/previous_hash + 脱敏)
AuditStore (append/get/query/get_chain/export/stats/verify + 接口化可换后端)
AuditQuery (10 筛选: project/task/agent/trace/type/actor/decision/status/risk/time)
AuditDecisionChain (get_chain 重建 Product→…→Delivery 决策链)
AuditExplain (结构化"为什么": why_created/why_agent/why_stopped/why_debug/why_cost/who_approved — 默认不调 LLM)
AuditContextBudget (Context 保护: candidates/selected/discarded/tokens)
AuditIntegrity (event_hash + previous_hash + verify — tamper-evident)
```

## 2. Capability Delivery

```
Core:
✅ AuditEvent + 33 EventType + redact + hash + seal
✅ AuditStore + AuditQuery + AuditDecisionChain + AuditExplain + AuditContextBudget + AuditIntegrity

CLI:
✅ audit events/trace/chain/decision/explain/task/agent/cost/export/stats (10 命令)
-h: ✅ action metadata + 11 意图关键词 ("查看审计记录"/"审计追踪"/"审计决策链"/
   "为什么创建这个任务"/"为什么选择这个Agent"/"为什么项目停了"/"审计任务"/
   "审计Agent"/"成本审计"/"导出审计"/"审计统计")

API:
✅ GET /api/audit/events | /trace/{id} | /chain/{id} | /task/{id} | /agent/{id}
✅ GET /api/audit/decisions | /cost/{project} | /stats
✅ POST /api/audit/explain | /export
schema: ✅ Pydantic + error handling; 注册: ✅ api/__init__.py (10 端点)

Tests:
✅ Core 168 + CLI/API/E2E 40 = 208 新测试 (五覆盖)
```

## 3. 真实 E2E 证据 (ScorePocket 数据)

```
CASE A: 决策链重建 — 11 事件, 根 DISCOVERY_COMPLETED → 最终 PROJECT_DELIVERED
CASE B: 为什么修 — "根因: 持久化缺失; 策略: FIX_CODE; 复用经验: exp-7"
CASE C: 谁批准 — alice (BUDGET_BLOCKED → REVIEW_APPROVED)
CASE D: 成本关联 — LLM_CALL 事件 + cost_reference
CASE E: 敏感信息 — api_key 不泄漏 (False) + 防篡改 (True)
```

## 4. 验收问题回答 (19 问关键)

| 问题 | 证据 |
|---|---|
| 谁做了什么? | actor_type/actor_id (user/system/agent/llm/tool) |
| 为什么做? | decision_reason + AuditExplain |
| 用了什么 Agent/LLM/Memory/Tool? | agent_id + references (memory/cost/debug) |
| 花了多少钱? | cost_reference 关联 CostLedger |
| 为什么触发 Governance? | policy/policy_result + BUDGET_BLOCKED 事件 |
| 谁批准了? | approval.reviewer (alice) |
| 为什么 Debug 采用这个策略? | DEBUG_STRATEGY_SELECTED + decision_reason |
| 第一次为什么失败? | TEST_FAILED 事件 + evidence |
| 最终 Artifact/影响? | artifact_reference + impact 字段 |
| 能否重建决策链? | get_chain (11 事件链) |
| 是否把整个历史塞进 LLM? | 否 (AuditExplain 默认结构化, ContextBudget 保护) |
| 敏感信息是否进入 Audit? | 否 (redact 验证 False 泄漏) |
| 能否检测篡改? | 是 (verify: 改 decision → False) |

## 5. 测试

```
新增: 208 (Core 168 + CLI/API/E2E 40)
全量: 11596 passed + 1 skipped, 0 failed (11388 基线 → +208, 零回归)
```

## 6. 修复的真实缺陷

- seal 不生成 audit_id (append 直收实例 → audit_id 空 → chain 无限递归) — 补 uuid
- explain 分发因 task_id/agent_id 已提供而跳过分发 — 关键词优先
- "为什么项目停了" 无匹配关键词 (子串不连续) — 补"停了"/"为什么停止"
- redact: password_hash 被 hash 后缀放行 — 敏感子串优先
- AuditStore(Path) 当 file 参数 → 嵌套目录 — 测试用 workspace 参数

## 7. 技术债

- Audit 未自动接入生产链 (当前手动 append; Adapter 半自动)
- Storage 为 JSON (接口化, 未来 SQLite/PG/ES)
- 无完整 IAM/RBAC/SSO (数据模型预留)
- AuditExplain LLM 模式未接 (结构化为主)

## 8. 下一阶段建议

```
S10-070 — CLI/API Completion (全面扫描所有能力: CLI 存在? API 存在? -h? Tests?)
  或 Audit 自动接入生产链 (orchestrator 自动 append 事件)
```

---

> S10-069 文档完毕 | Audit Intelligence | 208 新测试 | 11596 全绿
