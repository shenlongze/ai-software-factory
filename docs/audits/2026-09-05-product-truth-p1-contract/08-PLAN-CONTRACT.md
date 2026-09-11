# 08 — PLAN CONTRACT (P1 CONTRACT, 2026-09-05)

> D9: 唯一 Plan SSOT — 本阶段最重要

---

## 1. 现状拆解 (必须消除多 SSOT)

| 现存 | 分类 | 处置 |
|---|---|---|
| session_plans.json (16, session keyed) | ORCHESTRATION STATE (会话计划快照) | 降级: 只作会话投影/恢复状态; 不再是计划 truth |
| PLAN-{hex8} (Web 生成) | 计划 id (无独立 store — 存 console_sessions/session_topics/session_plans) | **保留前缀** → canonical plans store |
| session_topics / console_sessions 内嵌 plan | SESSION STATE | 保留会话历史; 非 domain |
| plan_development (agent_loop:358) | 计划生成器 (LLM 拆任务) | 改调 PlanService (生成 + 持久化 + 状态) |
| chain_start plan 消费 | orchestration | 从 canonical plan store 读 plan (含 plan_id) |

## 2. 冻结: 什么是 Plan

> Plan = 针对一个 PRD (或直连 Requirement) 的可执行任务分解快照
> (goal + tasks[] + order + acceptance + ask_approval), 经人工/系统批准后
> 生成 TASK-*。

- **唯一 canonical Plan identity**: PLAN-{hex8}
- **唯一 canonical store**: plans/plans.json (新)
- **唯一 canonical writer**: PlanService.create_plan (生成 → pending → approved)
- **不可变**: approved 后不改; 迭代 = 新 PLAN-*
- 生成器 (plan_development) 是 service 内部实现, 非独立 truth

## 3. 消除

PLAN-* + session_plans.json + console_sessions 三处快照 → 收敛:
- plans store = truth
- session_plans/console_sessions 内嵌 = 会话投影 (引用 plan_id, 不复制内容)
- 禁止以 session key 作为 plan identity

## 4. Plan 上游

plan.prd_id (可选, 有 PRD 时) / plan.requirement_id (MVP 直连, 兼容现状 4/16)
→ PRD version 引用见 06。
