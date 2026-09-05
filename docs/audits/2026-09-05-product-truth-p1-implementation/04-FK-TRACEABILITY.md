# 04 — FK / TRACEABILITY (P1 IMPL, 2026-09-05)

## 1. FK 落地

- discovery.idea_id → IDEA-*
- requirement.discovery_id → DISC-*
- prd.requirement_ids[] → REQ-*
- plan.prd_id + prd_version → PRD-*@vN (MVP: plan.requirement_id 直连)
- task.plan_id → PLAN-* (P0 create_task 已支持, E2E-1 真实)

## 2. Forward/Reverse

- forward_trace(idea) → {disc[], req[], prd[], plan[]}
- reverse_trace(task) → {task, plan, prd, prd_version, req, disc, idea, chain}
- 纯 canonical FK; 无 filename/audit/session 推断
- LEGACY task (无 plan_id) → 仅 task 级, 不伪造 (test_reverse_no_plan_legacy_task)

## 3. 真实 E2E-1

TASK-751f3807 → PLAN-7577fde3 → PRD-66282963@v2 → REQ-da79f24d → DISC-79d79678 → IDEA-3d45c5a2
