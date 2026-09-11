# 05 — RELATIONSHIP / FK CONTRACT (P1 CONTRACT, 2026-09-05)

> D5 + D6: Truth Graph 边 + FK + cardinality

---

## 1. 冻结关系 (业务语义决定)

| 边 | Cardinality | FK | 语义 |
|---|---|---|---|
| Idea → Discovery | 1:N | discovery.idea_id = IDEA-* | 一个 Idea 可多次 Discovery (重审) |
| Discovery → Requirement | 1:N | requirement.discovery_id = DISC-* | Discovery 收敛出多个 Requirement |
| Requirement → PRD | N:1 | prd.requirement_ids = [REQ-*] | 一个 PRD 覆盖多 Requirement (N→1); PRD→Requirement 1:N 反向 |
| PRD → Plan | 1:N | plan.prd_id = PRD-* | 一个 PRD 可多次 Plan (迭代) |
| Plan → Task | 1:N | task.plan_id = PLAN-* (P0 已支持) | Plan 生成多 Task |
| Plan → Requirement (旁路) | 可选 | plan.requirement_id 可保留 (兼容) | 当无 PRD 时 (MVP 路径) |

## 2. 允许

- PRD → multiple Requirements (requirement_ids[])
- Plan → multiple PRD? **否** (冻结: plan.prd_id 单值; 跨 PRD 计划 → 多 Plan)
- Task → multiple Plans? **否** (冻结: task.plan_id 单值; P0 contract)
- 无 PRD 的 Plan (Requirement → Plan 直连) = MVP 允许 (bridge 语义, 见 08)

## 3. FK 表达

显式 id 字段 (parent_id 嵌入 child), 不建 relation table (KISS);
无 PRD 时不引入中间表, 用可空 prd_id 表达。

## 4. 冻结图

```
User Intent (输入)
   ↓
IDEA-* ──1:N── DISC-* ──1:N── REQ-*
                                  │  (N:1)
                                  ▼
                               PRD-* ──1:N── PLAN-* ──1:N── TASK-*
                                  │  (直连 MVP: REQ → PLAN 可空 prd_id)
```
