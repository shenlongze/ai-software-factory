# S10-060 — GAP ANALYSIS

> 日期:2026-08-15 | Sprint: S10-060 | P0 现状审查
> 审查方式: 读取真实代码 (orchestrator/dependencies/decision/quality/team_state/conflicts/workspace)

---

## 已有能力 ✅ (可直接复用)

| 能力 | 位置 | 复用方式 |
|---|---|---|
| TaskDependencyGraph | dependencies.py | add_dependency/get/has/topological_order — Replanning 基础 |
| HandoffDecisionEngine | decision.py | 执行级决策 (CONTINUE/BLOCK/RETRY/REPAIR/SERIALIZE/SKIP/REQUEST_REVIEW) — Replanning 触发源之一 |
| ConflictResolver | conflicts.py | 冲突检测/解决 — Replanning 输入 |
| WorkspaceContext/Reservation | workspace.py | 上下文 + 文件锁 — Replanning 输入 |
| TeamExecutionState | team_state.py | 团队状态 — 需扩展 plan_version |
| ExecutionState | orchestrator.py | execution_state.json — 需扩展 replan 字段 |
| Validator/RepairManager | quality.py | 验证 + 任务级修复 — Repair 与 Replanning 边界 |
| ExecutionOrchestrator | orchestrator.py | team mode 执行 — Replanning 接入点 |
| AgentMatcher/Team | agents.py/teams.py | 新增任务角色分配 |

## 真正缺失 ❌ (S10-060 目标)

| # | 缺失 | 说明 |
|---|---|---|
| G1 | **ReplanningEngine** | 无计划级决策引擎 (KEEP_PLAN/INSERT_TASK/MODIFY_TASK/...) |
| G2 | **ReplanDecision** | 无 {decision, reason, affected_tasks, new_tasks, dependency_changes, execution_order} |
| G3 | **动态 Task 增删改** | DAG 有 add_dependency, 无 add_task/remove_task/modify_task |
| G4 | **Cycle Protection 显式** | topological_order 有环兜底, 但无 add_dependency 时拒绝循环 (需 BLOCK+reason) |
| G5 | **plan_version** | execution_plan/execution_state 无版本概念 |
| G6 | **replan_count/last_replan_reason/max_replan** | 无重规划限制 (防无限循环) |
| G7 | **replanning_decisions.json** | 无重规划决策资产 |
| G8 | **Orchestrator 接入** | execute→observe→decide→replan→update→continue 未实现 |

## 需要扩展 ⚠️

| # | 扩展 | 现状 → 需要 |
|---|---|---|
| H1 | TaskDependencyGraph | add_dependency → +add_task/remove_task/modify_task/add_dependency(带 cycle 拒绝)/remove_dependency/recalculate_order |
| H2 | ExecutionState | +plan_version/replan_count/last_replan_reason |
| H3 | TeamExecutionState | +plan_version (同步) |
| H4 | HandoffDecisionEngine | 执行级决策 → ReplanningEngine 消费其 BLOCK/REQUEST_REVIEW 触发重规划 |

## 不该现在做 🚫 (S10-060 边界)

- PyPI/GitHub marketing/SaaS/账号/Billing/云部署/多租户/Git merge/真正并行 DAG/Reviewer 大系统/UI
- 不重复: Team/Role/Handoff/Workspace/Conflict Detection/Workspace Reservation (S10-056~059 已完成)

---

## S10-060 设计方向

```
P1 ReplanningEngine (新 replanning.py):
  输入: execution_state/execution_plan/tasks/workspace_context/handoffs/decisions/
        validation_result/failure/agent_output/dependency_graph
  决策: KEEP_PLAN/REORDER_TASKS/INSERT_TASK/MODIFY_TASK/BLOCK_TASK/SKIP_TASK/
        SPLIT_TASK/REQUEST_REVIEW
  输出: ReplanDecision {decision, reason, affected_tasks, new_tasks,
        modified_tasks, dependency_changes, execution_order}
  落盘: replanning_decisions.json

P2 Task Graph 动态修改 (扩展 dependencies.py):
  add_task/remove_task/modify_task/add_dependency (cycle 拒绝→BLOCK+reason)/
  remove_dependency/recalculate_order

P3 Execution Plan 动态更新 (orchestrator):
  replan → 同步 execution_plan.json/execution_state.json/tasks.json + plan_version
  (v1→v2→v3, 可回答"为什么改变计划")

P4 Execution State 扩展:
  plan_version/replan_count/last_replan_reason + max_replan (缺省 5)
  > max → REQUEST_REVIEW

P5 Orchestrator 接入:
  execute task → observe result → Decision → 需 replan? → ReplanningEngine
  → 更新 DAG/Plan → 继续执行 (非简单 retry)

P6 Repair vs Replanning 边界:
  Repair: 当前任务失败 → retry (quality.py)
  Replanning: 计划不适合现实 → 改 DAG (replanning.py)
  → 两者独立, 不混淆

P7 真实 Replanning Pilot:
  ScorePocket + 故意缺口 (QA 发现缺 persistence layer → INSERT_TASK)
  → 真实 DeepSeek + ReplanningEngine → plan v1→v2 → DELIVERED
```

> GAP 完毕 | G1-G8 缺失 | H1-H4 扩展 | 边界明确 | Repair 与 Replanning 分离
