# 13 — DECISION LOG (P1 CONTRACT, 2026-09-05)

> D1-D20 逐项决策 (Decision/Reality/Alternatives/Reason)

---

## D1 — 六层 Product Domain

**Decision**: Idea/Discovery/Requirement/PRD/Plan = 新 domain entities; Task = P0;
User Intent = 输入事实 (非 entity)。
**Reality**: Idea 三语义 (S9 PI-*/Web feature/M3), Requirement 内联, PRD 纯文档,
Plan 编排快照。
**Alternatives**: ① 六层全实体化 ② 只实体化 REQ/PRD/PLAN (Idea 归 S9, Discovery 归
lifecycle) ③ User Intent 也实体化。
**Chosen**: ① (六层 + Intent 输入)。**Reason**: P0 证明唯一事实源是 traceability
前提; S9 Idea 域与主链脱节导致 G5; Discovery 有实现无数据 (需实体才可落盘);
Intent 是对话输入, 实体化无消费端 (INTENT-* 不必要)。
**Rejected**: ② (S9 idea 与执行链仍断); ③ (过度设计)。
**Impact**: 新 5 domain + 收敛 create_feature 语义。
**Boundary**: P1 Impl。

## D2 — Identity

**Decision**: IDEA-*/DISC-*/REQ-*/PRD-*/PLAN-*/TASK-*; 旧 PI-*/req_* = LEGACY。
**Reality**: PI-001 2 条 / req_{hex12} 7 条 / PLAN-{hex8} 3 处快照 / session key。
**Reason**: 统一前缀族 (对齐 P0 TASK-*); session_id/filename 禁止冒充 domain id。
**Rejected**: 保留 req_*/PI-* (历史语义 = M3 内联, 无 lifecycle)。

## D3 — Single Writer

**Decision**: 每 Entity 一 Service 唯一 writer (IdeaService/DiscoveryService/
RequirementService/PRDService/PlanService; Task=create_task P0)。
**Reality**: Idea 3 writer; Plan 2 上下文; REQ/PRD 单 writer 非 domain。
**Reason**: 消除多 writer (P0 铁律)。

## D4 — Lifecycle (见 04 文档)

## D5/D6 — FK/cardinality (见 05 文档)

## D7 — Versioning (见 06): PRD versioned; Plan immutable snapshot; Task 引 PRD version 经 Plan。

## D8 — Document Projection (见 07): PRD.md/product-definition.md = projection; 禁止反向。

## D9 — Plan SSOT (见 08): plans store + PLAN-*; session_plans 降级投影。

## D10 — Task Boundary (见 09): TASK-* 不动; plan_id 可选; 历史不 backfill。

## D11 — User Intent: 输入事实 (理由: 消费端=意图路由, 非 traceability 节点; 语义
经 Idea/Requirement 落 domain)。

## D12 — Discovery: truth = DISC-* entity (收敛事实), 非 conversation.json (会话状态) /
product-definition.md (投影) / DISCOVERY_CONFIRMED (event) / product_defined
(lifecycle 终态 — 保留作 org ProjectState)。

## D13 — Requirement: 需 store/service/lifecycle/version(轻)/provenance; 不因 req_*
存在而认可其 canonical。

## D14 — PRD: 三层边界 PRD-* entity + version + md 投影; generate_prd = 生成器
(调 PRDService); 禁止 PRD.md 升 canonical。

## D15 — Traceability: forward/reverse 纯 FK (见 12)。

## D16/D19 — Legacy: 全 LEGACY 不迁移不伪造 (见 10)。

## D17 — WebUI/API/CLI: 全经 Service (见 11); 现状违规点 (create_feature idea /
7438 PLAN 生成 / agent 内联 req) = P1 Impl 修复点。

## D18 — Event 边界: 观察非 SSOT (见 12)。

## D20 — P1→P0 边界: Plan→TASK-* 唯一; P1 不碰 run-*/EXS-*/art-*/ver-*/EVD-*。
