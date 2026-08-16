# S10-060 — Autonomous Replanning & Adaptive Production Loop

> 日期:2026-08-15 | Sprint: S10-060 | Autonomous Replanning
> 状态: AI Team 能够观察/发现计划偏差/自己重新规划/修改任务图/继续生产

---

## 1. 里程碑

```
旧: 失败 → Repair → retry (被动)
新: 执行 → 观察 → 发现偏差 → 分析 → 重新规划 → 修改 Task/DAG → 继续执行 (自主)
```

## 2. 新能力

| 能力 | 说明 |
|---|---|
| ReplanningEngine | 8 决策: KEEP_PLAN/REORDER_TASKS/INSERT_TASK/MODIFY_TASK/BLOCK_TASK/SKIP_TASK/SPLIT_TASK/REQUEST_REVIEW + reason |
| ReplanDecision | {decision, reason, affected_tasks, new_tasks, modified_tasks, dependency_changes, execution_order, plan_version, timestamp} |
| 动态 DAG | add_task/remove_task/modify_task/add_dependency(cycle 拒绝)/remove_dependency/recalculate_order |
| Cycle Protection | T1→T2→T3→T1 拒绝 + 图不变 (BLOCK, reason=cyclic) |
| plan_version | v1→v2→v3 演进 (execution_plan/state/tasks 同步) |
| replan 限制 | max_replan=5, 超限 → REQUEST_REVIEW |
| 决策资产化 | replanning_decisions.json |
| Repair vs Replanning 分离 | 任务失败 → Repair (quality.py); 计划偏差 → Replanning (replanning.py) |

## 3. 真实 Replanning Pilot (ScorePocket, 2026-08-15)

```
plan v1: 4 任务 (PM → Architect → Backend → QA) — 缺持久化
QA 发现缺口: "比赛记录需要持久化存储 — persistence layer missing"
ReplanningEngine → INSERT_TASK
  reason: "Agent 发现计划缺口 (missing): 计划缺 1 个任务, 插入后继续执行"
  new_tasks: [T005 实现持久化存储]
plan v2: 5 任务 (含 T005, backend-1)
真实执行: 5/5 completed | 26.8s | 真实 DeepSeek × 5
replanning_decisions.json 落盘 (INSERT_TASK)
验收 → DELIVERED
```

## 4. Orchestrator 接入 (真实流程)

```
execute task → observe result → 失败? → ReplanningEngine.decide
  INSERT_TASK → 新任务入 plan + DAG 更新 + plan_version+1 → 继续执行
  KEEP_PLAN  → Repair 路径不变 (任务级)
  REQUEST_REVIEW → 停止队列 (replan 超限)
非简单 retry: 计划级偏差 → 改 DAG
```

## 5. 测试

```
新增: test_session_replanning.py 100 passed (>=100 目标)
全量: 9963 passed + 1 skipped, 0 failed (基线 9863 → +100, 零回归)
覆盖: 8 决策/DAG mutation/cycle/plan_version/replan limit/orchestrator/repair vs replan
```

## 6. 回答完成标准

| 标准 | 状态 |
|---|---|
| ReplanningEngine | ✅ replanning.py |
| ReplanDecision | ✅ dataclass + to_dict/from_dict |
| 动态 Task 增删改 | ✅ add/remove/modify |
| 动态 Dependency 修改 | ✅ add/remove_dependency + recalculate |
| DAG cycle protection | ✅ DFS 可达性拒绝 |
| execution_plan version | ✅ plan_version v1→v2 |
| execution_state version | ✅ plan_version/replan_count/last_replan_reason |
| replanning_decisions.json | ✅ |
| Orchestrator 真正接入 | ✅ execute→observe→decide→replan→continue |
| Repair 与 Replanning 分离 | ✅ 独立路径 |
| 真实 Agent/LLM | ✅ 真实 DeepSeek × 5 |
| 真实 Replanning | ✅ INSERT_TASK (QA 发现缺口) |
| 真实新增 Task | ✅ T005 持久化 |
| 真实 Validation/Delivery | ✅ 5/5 + DELIVERED |
| 全量 0 failed | ✅ 9963 passed |
| git clean / commit / push | ✅ 7c94217 |

## 7. 技术债

- INSERT_TASK 候选由调用方提供(不自动生成任务内容)
- REQUEST_REVIEW 无人工审批 UI(接口预留)
- 决策记录版本=触发时版本(应用后 state 递增)
- SKIP 信号 "不再需要" 与 GAP "需要" 子串冲突已修复

## 8. 下一 Sprint 建议

```
S10-061 — 发布行动 (完整自主生产叙事就绪)
  "用户一句话 → AI 团队自主生产: 规划→执行→观察→重规划→交付"
  + 冲突避免 + 决策可解释 + 计划版本化
- 或 S10-061: INSERT_TASK 自动生成 (LLM 提议缺口任务)
```

---

> S10-060 文档完毕 | Autonomous Replanning | 100 新测试 | 9963 全绿
