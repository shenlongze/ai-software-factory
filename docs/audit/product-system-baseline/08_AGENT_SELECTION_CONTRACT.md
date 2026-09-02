# 08 — AGENT SELECTION CONTRACT (STEP 10, 2026-09-02)

## 冻结语义 (D-7)
```
Task ──► Capability Constraint ──► Router ──► Agent
```
- Agent 是执行能力, 不是 Task 本身
- Router 选择输入 = Task 描述 + Capability Constraint (能力需求)
- 现有证据: gateway._pick_executor → external_ai/router.route (classify_task + score_candidate,
  agents.json 8, execution_records 100) — CURRENT M3
- Task 上不得复制 Agent 属性作为事实 (经 selection 决策记录)

## 关系
- Task → Capability Constraint: CONTRACT-ONLY (语义冻结; 当前 router 以 task 文本分类)
- Capability Constraint → Agent: CURRENT (router)
