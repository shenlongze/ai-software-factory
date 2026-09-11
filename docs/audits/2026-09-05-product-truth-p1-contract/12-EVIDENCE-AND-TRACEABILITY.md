# 12 — EVIDENCE & TRACEABILITY (P1 CONTRACT, 2026-09-05)

> D15 + D18: Product Traceability + Event 边界

---

## 1. 冻结 Traceability 目标

### Forward (Idea → Task)
```
IDEA-* → DISC-* → REQ-* → PRD-* (version) → PLAN-* → TASK-*
FK: idea_id → discovery_id → requirement_ids → prd_id → plan_id
```

### Reverse (Task → Idea)
```
TASK-* --plan_id--> PLAN-* --prd_id--> PRD-*@vN
                    PLAN-* --requirement_id--> REQ-* --discovery_id--> DISC-* --idea_id--> IDEA-*
```

## 2. FK 汇总 (每级唯一父键)

| 级 | FK to parent | 反查 |
|---|---|---|
| Discovery | idea_id | Idea → Discovery[] |
| Requirement | discovery_id | Discovery → Requirement[] |
| PRD | requirement_ids[] | Requirement → PRD (N:1) |
| Plan | prd_id (或 requirement_id MVP) | PRD → Plan[] |
| Task | plan_id | Plan → Task[] |

## 3. Event / Audit 边界 (D18)

- DISCOVERY_CONFIRMED / product_defined / TASK_CREATED = event/lifecycle 观察
- 禁止 audit/event 反推 domain entity
- 禁止 event sourcing 重建 DISC-*/REQ-*/PRD-*/PLAN-* (domain store 是 truth)
- 每 Service 操作 emit 观察事件 (domain→event 单向)

## 4. 答案能力 (Implementation 后)

系统应可回答 "这个 TASK 来自哪个 Idea/Requirement/PRD/Plan" 与反向 —
纯 FK join (domain query), 非 audit 拼装。
