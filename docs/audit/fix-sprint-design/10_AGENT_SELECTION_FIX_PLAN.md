# 10 — AGENT SELECTION FIX PLAN (STEP11)

## 目标 (D-7, INV-008)
```
Task → Capability Constraint → Router → Agent
```

## 当前 (M3)
- gateway._pick_executor (gateway.py:18) → router.route (classify_task + score_candidate)
- agents.json 8; execution_records 100 (backend-1 等真实执行)
- Capability Constraint 语义: 以 task 文本分类 (无显式 constraint 字段)

## 缺口
- 显式 Capability Constraint 字段 ABSENT (router 靠文本分类)
- 角色 Agent (developer/pm/architect) 生产触发入口 UNKNOWN

## Fix 边界 (FX-06, 设计级)
1. 取证: 角色 Agent 类 (exec/developer.py 等) 谁调用 (CLI/旧系统) — 先验证再定
2. Task 携带 capability 需求 (可选字段) → router 输入
3. 角色 Agent 生产入口: 若证据显示无入口 → 注册进 gateway router 候选 (验证后)
不做: 新建 Agent / 重写 router
