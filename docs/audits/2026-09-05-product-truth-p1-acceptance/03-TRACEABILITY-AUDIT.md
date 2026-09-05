# 03 — TRACEABILITY AUDIT (P1 FINAL ACCEPTANCE, 2026-09-05)

> 反查纯 FK 验证 + 正查 + P1/P0 边界

---

## 1. Reverse trace (真实 E2E, fresh)

```
TASK-5fe43eba --plan_id--> PLAN-94f49add --prd_id+version--> PRD-ef6d328a@v2
                              --requirement_id--> REQ-600e99e9 --discovery_id-->
                              DISC-e73bc05e --idea_id--> IDEA-22bf6f79
```

每跳来源:
- task.plan_id → backlog task.json 字段 (P0 canonical, 只读)
- plan.prd_id / prd_version / requirement_id → plans store 字段
- prd.requirement_ids → prds store 字段
- req.discovery_id / disc.idea_id → stores 字段

**零推断**: 无 filename 匹配 / 无 title 匹配 / 无 session_id 推断 /
无 event 重建 / 无启发式 (reverse_trace 代码逐 FK 直查; 缺 FK → 诚实断链)。

## 2. Forward trace

forward_trace(idea) → disc[] (idea_id) → req[] (discovery_id) →
prd[] (requirement_ids 包含) → plan[] (prd_id 或 req_id)。

## 3. P1/P0 边界 (exact)

- P1 产物止于 TASK-* (plan_id 关联)
- run/EXS/art/ver/EVD 全部经 P0 既有路径 (E2E-1: TASK → _chain_task_run →
  record_invocation → finalize_node_run)
- product_truth.py 不含任何 P0 执行函数调用 (grep create_node_run/record_
  invocation/finalize 零命中 — 仅 E2E 脚本使用)

**PASS — 纯 FK trace, 边界精确**
