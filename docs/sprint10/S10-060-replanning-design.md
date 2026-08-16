# S10-060 — Autonomous Replanning & Adaptive Production Loop 设计

> 日期:2026-08-15 | Sprint: S10-060 | 设计 (基于 GAP 分析)
> 目标: AI Team 能够观察/发现计划偏差/自己重新规划/修改任务图/继续生产

---

## 1. 架构

```
                    ┌──────────────┐
                    │   Agent Team │
                    └──────┬───────┘
                           ↓
                        Execute
                           ↓
                        Observe
                           ↓
                     ┌───────────┐
                     │  Decide   │
                     └─────┬─────┘
                           ↓
                    ┌──────────────┐
                    │   Replan?    │
                    └───┬──────┬───┘
                        │      │
                       NO     YES
                        │      │
                        │   Replan
                        │      ↓
                        │   Update DAG
                        │      ↓
                        └──→ Execute
                               ↓
                           Validate
                               ↓
                            Repair
                               ↓
                            Deliver
```

## 2. P1: ReplanningEngine (新增 replanning.py)

```
输入: execution_state / execution_plan / tasks / workspace_context / handoffs /
      decisions / validation_result / failure / agent_output / dependency_graph
决策: KEEP_PLAN / REORDER_TASKS / INSERT_TASK / MODIFY_TASK / BLOCK_TASK /
      SKIP_TASK / SPLIT_TASK / REQUEST_REVIEW
输出: ReplanDecision {decision, reason, affected_tasks, new_tasks,
      modified_tasks, dependency_changes, execution_order, plan_version}
落盘: replanning_decisions.json

规则:
  - 无偏差 → KEEP_PLAN
  - 前序结果改变依赖 → REORDER_TASKS
  - Agent 发现缺口 (缺 API contract/persistence) → INSERT_TASK
  - 任务内容过时 → MODIFY_TASK
  - 依赖不成立 → BLOCK_TASK
  - 任务不再需要 → SKIP_TASK
  - 任务过大 → SPLIT_TASK
  - 需人工 → REQUEST_REVIEW (含 replan 超限)
```

## 3. P2: Task Graph 动态修改 (扩展 dependencies.py)

```
add_task / remove_task / modify_task / add_dependency / remove_dependency / recalculate_order
Cycle Protection: add_dependency 检测环 (T1→T2→T3→T1) → 拒绝 + BLOCK + reason
```

## 4. P3: Execution Plan 动态更新

```
replan → 同步 execution_plan.json / execution_state.json / tasks.json
plan_version: v1 → replan → v2 → replan → v3
最终可回答: AI Factory 为什么改变了原来的开发计划?
```

## 5. P4: Execution State

```
+plan_version / replan_count / last_replan_reason
+max_replan = 5 (防无限循环); 超过 → REQUEST_REVIEW
```

## 6. P5: Orchestrator 接入

```
execute task → observe result → Decision → 需 replan?
  YES → ReplanningEngine → 更新 DAG/Plan → 继续执行
  NO  → 继续
非简单 retry
```

## 7. P6: Repair vs Replanning 边界

```
Repair:    当前任务失败 → retry (quality.py RepairManager)
Replanning:计划不适合现实 → 改 DAG (replanning.py ReplanningEngine)
→ 独立, 不混淆
```

## 8. P7: 真实 Replanning Pilot

```
ScorePocket + 故意缺口: QA 发现比赛记录缺 persistence layer
→ QA → Handoff → Decision → ReplanningEngine → INSERT persistence task
→ 修改 DAG → Backend → Frontend → QA → DELIVERED
→ 真实 DeepSeek, plan v1 → v2, 非伪造
```

## 9. 模块计划

```
新增: factory-console/session/replanning.py
修改: dependencies.py (DAG mutation + cycle) / orchestrator.py (接入 + plan_version)
      / team_state.py (plan_version)
新增: tests/console/test_session_replanning.py (>=100)
```

## 10. 边界

- 不做: PyPI/marketing/SaaS/账号/Billing/云/多租户/Git merge/并行 DAG/Reviewer/UI
- 不重复: Team/Role/Handoff/Workspace/Conflict (S10-056~059)

---

> 设计完毕 | ReplanningEngine + DAG mutation + plan_version + Orchestrator 接入 + 真实 Pilot
