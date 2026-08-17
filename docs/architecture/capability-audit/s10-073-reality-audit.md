# S10-073 — Repository Reality Audit (Project Isolation + Audit Coverage)

> 日期: 2026-08-17 | Phase 0: 先找 Gap, 不写代码
> 方法: 代码事实扫描 (未修改代码)

---

## 一、Project Scope 现状 (真实)

| 数据 | 存储位置 | Scope | 隔离机制 | 风险 |
|---|---|---|---|---|
| ExperienceStore | workspace/memory/experience_store.json | **Workspace 级共享** | record.project 字段过滤 (可选) | FAIL-OPEN |
| AuditStore | workspace/audit/audit_events.json | **Workspace 级共享** | event.project_id 过滤 (可选) | FAIL-OPEN |
| 项目资产 | workspace/projects/<slug>/*.json | Project 级 (目录隔离) | 物理目录 | ✅ 安全 |
| DebugTrace/Session | workspace/debug_*.json | Workspace 级 | 字段过滤 | FAIL-OPEN |

## 二、Multi-Project Isolation Gaps (P0-A)

### 检索 FAIL-OPEN (5 处)

| # | 调用点 | project 传参 | 风险 |
|---|--------|-------------|------|
| 1 | actions.memory_search (L2038) | ❌ 不传 | 检索全部项目经验 |
| 2 | recommend_for_debug (L93) | ❌ 不传 | 推荐跨项目 |
| 3 | DebugRetrievalPolicy.retrieve (L129) | ❌ 不传 | Debug 经验跨项目 |
| 4 | DebugExperienceRetriever._retrieve_via_orchestrator (L69) | ❌ 不传 | Debug 经验跨项目 |
| 5 | DebugExperienceRetriever.retrieve (L111) | ⚠️ case.project (可能空) | 空 → 全量 |

**核心**: "调用者自觉传 project_id" + fail-open(不传 → 全 workspace 查询)。

### Cache/Singleton

- ✅ 无 lru_cache/singleton/全局缓存 (无缓存泄漏风险)

### Audit Query

- AuditStore.query(**filters) project_id 可选 (fail-open)

## 三、Audit Coverage (P0-B) — 实际 9/16

| 阶段 | 状态 | 事件 | 可接线点 |
|------|------|------|----------|
| DISCOVERY | ❌ | 无 | discovery.py 确认点 |
| PRODUCT | ✅ | PRODUCT_CREATED | — |
| INTELLIGENCE | ✅ | PRODUCT_INTELLIGENCE | — |
| PLAN | ❌ | 无 | orchestrator.prepare_project |
| AGENT | ❌ | 无 | orchestrator._run_queue (per-task) |
| EXECUTION | ❌ | 无 | 同 AGENT |
| TOOL | ❌ | 无 | agents.py 工具调用 (复杂) |
| CODE | ❌ | 无 | artifact 创建 (复杂) |
| TEST | ❌ | 无 | orchestrator validator.save |
| DEBUG | ✅ | DEBUG_STARTED | — |
| REPAIR | ✅ | REPAIR_COMPLETED/FAILED | — |
| GOVERNANCE | ✅ | GOVERNANCE_CHECK | — |
| REVIEW | ✅ | REVIEW_APPROVED | — |
| MEMORY | ✅ | MEMORY_LEARNED | — |
| DELIVERY | ✅ | PROJECT_DELIVERED | — |

> 注: S10-072 报告 10/16 含 VALIDATION_*; 按 16 阶段标准实际 9/16, 缺口 7。

## 四、本项目修复优先级

| Priority | Gap | 方案 | 复杂度 |
|----------|-----|------|--------|
| P0-A1 | 检索 fail-open (5 处) | unified.retrieve_experience 强制 project (fail-closed) | 低 |
| P0-A2 | ExperienceStore.records 默认全量 | 调用方强制传 project (检索路径) | 低 |
| P0-A3 | Audit query fail-open | audit_project 查询强制 scope | 低 |
| P0-B1 | PLAN 自动 | prepare_project → PLAN_CREATED | 低 |
| P0-B2 | TEST 自动 | validator.save → TEST_PASSED/FAILED | 低 |
| P0-B3 | AGENT/EXECUTION 自动 | _run_queue per-task → AGENT_STARTED/COMPLETED | 中 |
| P0-B4 | DISCOVERY 自动 | discovery 确认 → DISCOVERY_COMPLETED | 中 |

## 五、结论

- 物理项目资产 (projects/<slug>/) 隔离 ✅
- 逻辑资产 (Memory/Audit) 共享 + fail-open ❌ (P0-A 核心)
- Audit 缺口 7 阶段, 优先 PLAN/TEST/AGENT (可接线点明确)
- TOOL/CODE 事件复杂, 本 Sprint 评估 (若接线点侵入大 → 标记 PARTIAL 并解释)
