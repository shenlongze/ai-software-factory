# S10-070 — GAP ANALYSIS & ARCHITECTURE (CLI/API Completion & Production Integration)

> 日期:2026-08-17 | Sprint: S10-070 | Integration / Completion / Contract
> 原则: Capability = Core + CLI + API + Intent + Help + Test (+ Audit/Memory/Context Budget)

---

## 一、Capability Inventory (真实扫描)

```
CLI action (57): accept_project/agent.execute_task/agent_reason/audit_*(10)/
  create_product/create_project/debug_*(9)/discovery_start/execute_project/
  factory_*(3)/generate_prd/list_projects/memory_*(5)/prepare_project/
  product_*(5)/production_session_view/project_progress/repair_task/
  resume_project/review_*(4)/show_status/task_owner/team_*(4)/workforce

API 端点 (~60): audit_*(10)/debug_*(9)/memory_*(5)/product_intelligence_analyze/
  product_market_analysis/product_persona/list_projects/get_*/start_*/update_* 等

Intent 规则 (55): 覆盖 discovery/product/debug/memory/audit/review/team/execution
```

## 二、GAP 汇总

| # | GAP | 影响 |
|---|---|---|
| G1 | **API 缺 product_mvp/product_value** | CLI 有 API 无 → 违反 Capability Contract |
| G2 | **Audit 未自动接入生产链** | S10-069 limitation: 手动 append |
| G3 | **Memory 无自动沉淀** | 生产后需手动 factory memory learn |
| G4 | **无统一 Context Budget 总约束** | 各模块独立 budget, 组合可无限叠加 |
| G5 | **无统一 Retrieval abstraction** | 每个 Agent 各查各的, 未来多 RAG 无法编排 |
| G6 | **无 Capability Contract Test** | 无法自动保证"能力缺 CLI/API → 测试失败" |
| G7 | **无 CLI-only/API-only/NL E2E** | 未证明用户可用外部入口完成全生命周期 |

## 三、架构

```
1. API 补齐: api/product_intelligence.py 加 product_mvp/product_value (同一 Core)
2. AuditEmitter (audit/audit_emitter.py):
     emit(event_type, **fields) → AuditStore.append
     orchestrator/actions 关键点自动 emit (薄接入, 不重写)
3. Memory 自动沉淀 (memory/auto_learn.py):
     AutoLearner.learn_from_workspace(workspace) → ExperienceExtractor → Store
     production 完成/失败时自动调用 (薄接入)
4. ContextBudget 统一 (audit/context_budget.py 扩展或新 context_ledger.py):
     MAX_CONTEXT_TOKENS 总预算 + 各来源 allocation (system/task/project/memory/audit/debug)
5. Retrieval abstraction (retrieval/ 新包):
     RetrievalRequest/RetrievalCandidate/RetrievalScore/RetrievalSource/
     RetrievalPolicy/RetrievalBudget + RetrievalOrchestrator (去重/排序/Top-K/Budget)
     Retriever 注册: experience/audit/project (ExternalRAG future)
6. Capability Contract Test (tests/console/test_capability_contract.py):
     对每个 capability 自动检查: Core/CLI/API/Intent/Help/Tests 存在
7. E2E (CASE A-F): 真实 ScorePocket 全链 + CLI-only + API-only + NL + Governance + Memory
```

## 四、Capability Delivery Contract (永久规则)

```
Every production capability MUST ship with:
1. Core  2. CLI  3. API  4. Intent (适用时)  5. Help/-h
6. Unit tests  7. Integration tests  8. E2E (适用时)
9. Audit integration (生产决策/事件)  10. Memory integration (可学习经验)
11. Context Budget (历史/检索上下文)

禁止: "后续补 CLI" / "后续补 API" / "内部可调用所以算完成"
未来 Web UI: Web UI → API → Core (现在 API 必须存在)
```

## 五、测试计划 (150+)

```
Capability Contract (>=30): 每能力 Core/CLI/API/Intent/Help/Tests 存在
Audit 自动接入 (>=20): orchestrator 关键事件自动 emit
Memory 自动沉淀 (>=15): AutoLearner
Context Budget (>=15): 总预算不超限
Retrieval abstraction (>=15): Orchestrator/去重/Top-K/Budget
CLI-only E2E (>=10) / API-only E2E (>=10) / NL E2E (>=10)
ScorePocket 完整 E2E (>=10) / Governance E2E (>=10) / Memory E2E (>=10)
```

## 六、不该做 🚫

```
重写 Core/Memory/Debug/Audit (最小侵入)
复杂数据库 / 外部 RAG / Web UI / 新 Agent / 大量新 CLI
```

---

> GAP+架构完毕 | G1-G7 | Capability Contract 永久规则 | Integration Sprint
