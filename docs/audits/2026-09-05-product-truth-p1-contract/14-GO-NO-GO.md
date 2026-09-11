# 14 — GO / NO-GO (P1 CONTRACT FREEZE, 2026-09-05)

> 最终判定

---

## 1. 完整契约表

| Entity | Canonical? | ID | Store | Writer | Lifecycle | Version | Parent | Child | Cardinality | Projection | Legacy |
|---|---|---|---|---|---|---|---|---|---|---|---|
| User Intent | 否 (输入) | (session message) | console_sessions | — | — | — | — | Idea/Requirement | — | session title | — |
| Idea | **是** | IDEA-{hex8} | ideas store | IdeaService | created→refined→validated→approved→rejected/archived | 否 | — | Discovery[] | 1:N | (想法卡) | PI-* (S9) |
| Discovery | **是** | DISC-{hex8} | discoveries store | DiscoveryService | pending→running→completed(product_defined) | 否 | idea_id | Requirement[] | 1:N | product-definition.md | conversation.json (会话) |
| Requirement | **是** | REQ-{hex8} | requirements store | RequirementService | draft→validated→approved→superseded/rejected | 轻 (supersede) | discovery_id | PRD (N:1); Plan (MVP 直连) | 1:N→PRD | 需求卡 | req_{hex12} (7) |
| PRD | **是** | PRD-{hex8} | prds store (+versions) | PRDService | draft→approved→superseded→archived | **是** (每 approved) | requirement_ids[] | Plan[] | 1:N | PRD.md | 旧 PRD.md (6) |
| Plan | **是** | PLAN-{hex8} | plans store | PlanService | pending→approved→executing→completed→cancelled | 否 (immutable snapshot) | prd_id (或 req_id) | Task[] | 1:N | 会话计划卡 | session_plans (编排) |
| Task | **是 (P0)** | TASK-{hex8} | backlog | service.create_task | P0 冻结 | 否 | plan_id (可选) | run-* (P0) | 1:N→run | API/WebUI | 历史无 provenance 任务 |

## 2. 冻结 Truth Graph

```
User Intent (输入事实)
     │
     ▼
   IDEA-* ──1:N──► DISC-* ──1:N──► REQ-*
                                    │  N:1 (requirement_ids[])
                                    ▼
                                  PRD-* (@version) ──1:N──► PLAN-* ──1:N──► TASK-*
                                    ▲                          │ (MVP: req_id 直连, prd_id 可空)
                                    └──────────────────────────┘
     ▼
══════════════════════════
     P0 EXECUTION TRUTH (不重定义)
══════════════════════════
   run-* → EXS-* → art-* → ver-* → EVD-*
```

## 3. GO Gate

| 条件 | 状态 |
|---|---|
| Domain Entity 明确 (6+Task) | ✓ |
| Identity 明确 (IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*/TASK-*) | ✓ |
| Single Writer 明确 (每 Entity 一 Service) | ✓ |
| Lifecycle 明确 (每 Entity 独立) | ✓ |
| FK/cardinality 明确 (1:N 逐边 + N:1 PRD) | ✓ |
| Plan SSOT 明确 (plans store 唯一; session_plans 降级) | ✓ |
| PRD domain/document 边界明确 (PRD-* truth; PRD.md 投影) | ✓ |
| Legacy boundary 明确 (PI-*/req_*/旧 PLAN-*/旧 PRD.md/M3 全隔离) | ✓ |
| P1→P0 boundary 明确 (Plan→TASK-* 唯一; 不碰 run/EXS/art/ver/EVD) | ✓ |
| 无 P0 contract conflict | ✓ (P0 conflict: NO) |

## 4. STOP conditions 检查

1-16 全未触发: 无多 canonical ledger (Idea 三义已收敛决策) / 无多 writer 未决 /
无 domain-session id 冲突 (前缀族) / PRD.md 可安全抽象 (规则生成可复现) /
Plan owner 已定 (PlanService) / Task 无第二 ledger / WebUI/Agent 违规点已列
(P1 Impl 修复) / 不需改 P0 / 不需迁移 (新链 only) / 不伪造 FK / 不用 event 重建。

## 5. 最终判定

```
P1 PRODUCT TRUTH CONTRACT FREEZE
================================

Status: GO (contract 级 — 待人工批准进入 Implementation)

P1 Product Truth Chain: User Intent → IDEA-* → DISC-* → REQ-* → PRD-* → PLAN-* → TASK-* → P0
D1-D20: 全部冻结 (见 13-DECISION-LOG)
P0 Conflict: NO
Code Changes: 0
Data Changes: 0
Git Changes: 0

核心问题回答:
在当前架构下, P1 Product Truth Contract 是否已足够明确可进入 Implementation?
YES → GO (六层 domain + 唯一 identity/writer/store/lifecycle/FK + legacy 边界
      + P1→P0 边界全部冻结; 无 P0 conflict)
```

## 6. Implementation 范围预告 (不执行)

P1 Impl = 5 domain (Idea/Discovery/Requirement/PRD/Plan) + store/service +
收敛违规点 (create_feature idea → IdeaService; 7438 → PlanService; agent 内联
req → RequirementService; generate_prd → PRDService) + Plan→Task FK 完整 +
只读 CLI/API + 真实 E2E。仅新链 canonical; 历史 LEGACY 不动。
