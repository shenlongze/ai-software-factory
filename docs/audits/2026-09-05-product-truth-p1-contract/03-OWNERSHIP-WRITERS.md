# 03 — OWNERSHIP / WRITERS (P1 CONTRACT, 2026-09-05)

> D3: 唯一 canonical writer

---

## 1. 冻结 Ownership

| Entity | Canonical Store | Canonical Writer (唯一) | 现状 writer | 判定 |
|---|---|---|---|---|
| Idea | product/ideas.json (S9 store 扩展为 IDEA-*) 或新 store | IdeaService.create_idea | ProductService (PI-*) / Web create_feature / demo | 收敛: Web create_feature idea 改走 IdeaService (不再是 task 树 feature); demo 隔离 |
| Discovery | discovery/discoveries.json (新) | DiscoveryService.complete_discovery | service.complete_discovery (实现) | 唯一 writer 已存在 → 只加 entity id/store |
| Requirement | requirements/requirements.json (schema 升级 REQ-*) | RequirementService.create_requirement | agent_loop 内联 | agent_loop 内联改调 RequirementService |
| PRD | prd/prds.json (新) | PRDService.generate | actions.generate_prd (规则) | generate_prd 改调 PRDService (entity+version); PRD.md 投影由 service 写 |
| Plan | plans/plans.json (新, PLAN-*) | PlanService.create_plan | fastapi_adapter:7438 + chain_start | 两处改调 PlanService |
| Task | backlog (P0) | service.create_task (P0) | 同 | 不动 |

## 2. 现状多 writer 清单 (P1 必须消除)

- Idea: ProductService / Web action (create_feature) / demo → 3
- Plan: fastapi_adapter (Web 生成) + chain_start (session 编排消费) → 需单 service
- Requirement/PRD: 单 writer 但非 domain (内联/规则)

## 3. 原则

- 一个 Entity 一个 canonical writer (Service)
- Agent/WebUI/CLI 一律经 Service (D17)
- 禁止 event reconstruction / file direct write
