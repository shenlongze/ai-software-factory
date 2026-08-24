# Audit System 审计

> 代码事实扫描 (2026-08-17)

## 一、企业级审计维度检查

| 维度 | 状态 | 证据 |
|---|---|---|
| WHO (谁执行) | ✅ | actor_type (user/system/agent/llm/tool) + actor_id |
| WHAT (做了什么) | ✅ | event_type + action |
| WHEN | ✅ | timestamp (UTC ISO) |
| WHERE | ⚠️ | workspace_id/project_id 字段有, 自动填充不全 |
| WHY | ✅ | decision_reason + AuditExplain |
| HOW | ⚠️ | 无统一 method 字段 (metadata 可扩展) |
| WITH WHAT | ⚠️ | agent_id/model/tool 字段有, LLM_CALL 未自动 |
| RESULT | ✅ | result/status/outcome |
| COST | ⚠️ | cost_reference 关联, LLM_CALL 详情未自动 |
| RISK | ✅ | risk 字段 |
| POLICY | ✅ | policy/policy_result (BUDGET_BLOCKED 实证) |
| APPROVAL | ✅ | approval {reviewer, decision} (REVIEW_APPROVED 实证) |
| EVIDENCE | ✅ | evidence 字段 (脱敏) |
| IMPACT | ⚠️ | impact 字段有, 自动填充不全 |

## 二、能力矩阵

| Audit 能力 | Core | CLI | API | 自动覆盖 |
|---|---|---|---|---|
| Event Capture | ✅ | ✅ | ✅ | ⚠️ 5 action (见下) |
| Decision Chain | ✅ | ✅ | ✅ | — |
| Explainability | ✅ | ✅ | ✅ | — |
| Integrity/Hash | ✅ | ✅ | ✅ | ✅ (append 自动 seal) |
| Redaction | ✅ | ✅ | ✅ | ✅ (redact 内置) |
| Cost 关联 | ✅ | ✅ | ✅ | ⚠️ reference 有, 自动填充少 |
| Context Budget | ✅ | — | — | ❌ 未接 LLM |

## 三、自动覆盖检查 (生产链)

| 阶段 | 自动 Audit? | 证据 |
|---|---|---|
| Discovery | ❌ | 无 DISCOVERY_* 自动 emit |
| Product | ✅ | PRODUCT_CREATED/PRODUCT_INTELLIGENCE |
| Planning | ❌ | 无 PLAN_CREATED 自动 (emit_production 手动) |
| Agent | ❌ | 无 AGENT_STARTED 自动 |
| Tool | ❌ | 无 TOOL_CALL 自动 |
| Code | ❌ | 无 ARTIFACT_CREATED 自动 |
| Test | ❌ | 无 TEST_* 自动 |
| Debug | ✅ | DEBUG_STARTED |
| Repair | ❌ | 无 REPAIR_* 自动 |
| Governance | ❌ | 无 GOVERNANCE_CHECK 自动 (手动) |
| Review | ✅ | REVIEW_APPROVED |
| Delivery | ❌ | PROJECT_DELIVERED 手动 (emit_production) |
| Memory | ✅ | MEMORY_LEARNED |
| Learning | ❌ | 无独立 Learning 事件 |

**自动覆盖: 5/16 阶段 (31%)** — P0-4 最大缺口。

## 四、完整性/安全

| 检查 | 状态 | 证据 |
|---|---|---|
| API Key 不进 Audit | ✅ | redact 黑名单 + 测试验证 0 泄漏 |
| Secret/Password | ✅ | 敏感子串优先 (S10-069 修复) |
| 原始 Prompt 不落盘 | ✅ | 只存 reference/hash/summary |
| 时间戳 | ✅ | 全部 UTC ISO |
| ID 唯一 | ✅ | seal 生成 uuid4 |
| Trace 关联 | ✅ | trace_id/correlation_id/parent_event_id |
| 防篡改 | ✅ | event_hash + previous_hash + verify |
| 不可被业务修改 | ⚠️ | JSON 可写, 无 immutable 层 (基础 hash 检测) |

## 五、结论

Audit **模型/查询/解释/完整性完整真实**;
**生产自动捕获仅 31%** — orchestrator 执行链需接入 (P0-4)。
