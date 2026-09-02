# 03 — TASK DOMAIN CONTRACT (STEP 10, 2026-09-02) — 第一重点

## 四实体语义 (为什么不能混为一谈)

| 实体 | 是什么 | 谁创建 | 谁拥有/写 | 谁只读 | SSOT/投影 | 证据 |
|------|--------|--------|-----------|--------|-----------|------|
| Plan (Planning Entity) | 计划事实 (含 task 意图+顺序) | plan_development | PendingPlanStore | execute_plan | SSOT: session_plans.json | PLAN-* |
| Task (Execution Task) | 生产执行任务事实 (八态) | execute_plan/create_task | ManagementStore/transition | ExecState/UI | SSOT: backlog | TASK-* |
| Run | 一次运行事实 | gateway_execute | registry | ExecState/回写 | SSOT: registry | EXS-*/R* |
| ExecutionRecord | 执行过程事实 (agent/结果/错误) | exec 执行 | exec store | 审计/查询 | SSOT: exec records | EXS-* |

## 关系 (单向下钻, INV-005)
```
Plan ──produces──► Task ──creates──► Run ──produces──► {ExecutionRecord, Artifact, Verification}
   SSOT             SSOT                SSOT               SSOT (各 Domain 内)
```
每步: 创建者持有上游引用 (plan_id / task_id / run_id), 不允许反向修改上游事实。

## 三套 Task Truth 归属 (INV-012 落实)
| 现有结构 | 正式语义 | 角色 |
|---------|---------|------|
| backlog TASK-* | Execution Task Domain SSOT | 生产主链 SSOT (保留) |
| execution_plan T-* | 历史/计划产物语义 | 不得继续为独立平行 Task SSOT (不再写入新事实) |
| factory-exec T00x | Execution Record Domain (员工执行记录) | Runtime 域 (独立 Domain, 引用对齐) |

## 禁止状态
- Task 拥有第二份 Artifact/Verification 事实 (归 Run/Record)
- execution_plan 继续作为平行可写 Task SSOT
- Plan 反向被 Task/Run 修改
