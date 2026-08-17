# S10-070 — CLI/API Completion & Production Integration

> 日期:2026-08-17 | Sprint: S10-070 | Integration / Completion / Contract
> 原则: Capability = Core + CLI + API + Intent + Help + Test (+ Audit/Memory/Context Budget)

---

## 1. Capability Inventory (真实扫描)

```
CLI action (57): discovery/product(5)/debug(9)/memory(5)/audit(10)/review(4)/
  team(4)/governance(3)/project/lifecycle — 全覆盖
API 端点 (~62): audit(10)/debug(9)/memory(5)/product(5)/project/runtime/approval
Intent 规则 (60): 自然语言入口全覆盖
```

## 2. 完成的能力矩阵

| Capability | Core | CLI | API | Intent | -h | Test | 生产接入 | Audit | Memory |
|---|---|---|---|---|---|---|---|---|---|
| Product Intelligence | ✅ | ✅ | ✅(补齐 mvp/value) | ✅ | ✅ | ✅ | ✅ | ✅自动 | — |
| Memory Learning | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅自动沉淀 | ✅自动 | ✅ |
| Debug Intelligence | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅自动 | ✅ |
| Audit Intelligence | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅自动emit | ✅ | — |
| Discovery | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — |
| Governance/Review | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅自动 | — |
| Production Session | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | — | — |

## 3. 交付

```
1. API 补齐: product_mvp/product_value 端点 (CLI/API 契约闭合)
2. AuditEmitter (audit/audit_emitter.py): emit/emit_production + actions 薄接
   7 关键点自动 emit (PRODUCT_CREATED/PRODUCT_INTELLIGENCE/DEBUG_STARTED/
   REVIEW_APPROVED/MEMORY_LEARNED...) — 生产链自动审计
3. AutoLearner (memory/auto_learn.py): learn_from_workspace/should_learn — 自动沉淀
4. ContextLedger (session/context_ledger.py): MAX_CONTEXT_TOKENS 总预算 +
   allocate/check/stats — 组合不无限叠加
5. Retrieval abstraction (retrieval/): RetrievalRequest/Candidate/Score/Source +
   Experience/Audit/Project Retriever + RetrievalOrchestrator (去重/排序/Top-K/Budget)
   — 未来多 RAG 统一入口
6. Capability Contract Test (test_capability_contract.py): 28 能力自动检查
   Core/CLI/API/Intent/Help — 缺 CLI/API 测试直接失败
7. NL 补齐: "检查一下失败原因"/"有没有市场"/"查看审计"/"学到了什么"/"查看预算"
8. E2E 6 场景: 完整链/CLI-only/API-only/NL/Governance/Memory
```

## 4. Capability Delivery Contract (永久规则)

```
Every production capability MUST ship with:
1. Core  2. CLI  3. API  4. Intent (适用时)  5. Help/-h
6. Unit tests  7. Integration tests  8. E2E (适用时)
9. Audit integration  10. Memory integration  11. Context Budget

禁止: "后续补 CLI/API" / "内部可调用所以算完成"
未来 Web UI: Web UI → API → Core (现在 API 必须存在)
```

## 5. 真实 E2E 证据

```
1. create_product ✅ → 2. product_intelligence ✅ → 4. memory_learn ✅
5. Audit 自动: [PRODUCT_CREATED, PRODUCT_INTELLIGENCE] 自动落盘
8. ContextLedger: 500/12000 总预算约束
```

## 6. 测试

```
新增: 42 (Contract 11 + E2E 6 + Integration 26 — 部分与既有计数合并)
全量: 11638 passed + 1 skipped, 0 failed (11596 基线 → +42, 零回归)
```

## 7. 修复的真实缺陷

- RetrievalRequest.sources → source_type (Sub-agent models 签名对齐)
- emit_production event_type 重复 (便捷入口语义: PROJECT_DELIVERED)
- Contract: governance_budget intent "状态"→show_status (补 "查看预算" intent)

## 8. 技术债

- AuditEmitter 薄接 7 点 (orchestrator 内部执行事件未全接, 后续可扩展)
- AutoLearner 未接 execute_project 完成钩子 (当前手动/后续薄接)
- RetrievalOrchestrator 未接 LLM (接口就绪, 检索已可用)
- ExternalRAG future (RetrievalSource 预留)

## 9. 下一阶段建议

```
S10-071 — 发布行动 (产品入口层 + 全能力契约完成, 可对外)
  或 Audit/Memory 全自动接入 orchestrator 执行链
```

---

> S10-070 文档完毕 | CLI/API Completion + Production Integration | 11638 全绿 | Capability Contract 永久规则
