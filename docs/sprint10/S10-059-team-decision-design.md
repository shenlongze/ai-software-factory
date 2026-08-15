# S10-059 — Autonomous Team Decision & Workspace Isolation 设计

> 日期:2026-08-15 | Sprint: S10-059 | 设计 (基于 GAP 分析)
> 目标: Agent 团队从"顺序执行"升级为"理解上下文/交接/判断冲突/自主决策"

---

## 1. 架构

```
旧: Agent 完成 → 记录 Handoff → 下一个 Agent 执行
新: Agent 完成 → Handoff → DecisionEngine → Workspace 更新
     → 判断下一 Agent 上下文 → 检查依赖/冲突 → 执行策略 → 下一 Agent
```

## 2. P1: HandoffDecisionEngine (新增 decision.py)

```
输入: completed task / artifact / handoff / workspace_context / next task
      / dependencies / conflicts / agent role
输出: {decision, reason, conflicting_tasks, strategy}
决策: CONTINUE | BLOCK | RETRY | REPAIR | SERIALIZE | SKIP | REQUEST_REVIEW
规则:
  - 无冲突 + 依赖满足 → CONTINUE
  - 依赖未满足 → BLOCK
  - 前序失败可重试 → RETRY
  - 前序失败不可重试 → REPAIR
  - 同文件冲突 → SERIALIZE (等待前序释放)
  - 任务不再需要 → SKIP
  - 需人工评审 → REQUEST_REVIEW
落盘: handoff_decisions.json
```

## 3. P2: Workspace Isolation (扩展 workspace.py)

```
新增字段: active_agent/active_task/reserved_files/workspace_snapshot/changed_files
acquire_reservation(agent, task, files): 文件写权限锁定 (已被占 → BLOCK)
release_reservation(agent, task): 释放 + changed_files 记录
核心: 同一文件不能被两个 Agent 同时拥有写权限
落盘: workspace_locks.json
```

## 4. P3: ConflictResolver 参与执行 (升级 conflicts.py)

```
detect → classify (NO_CONFLICT/SERIALIZE/RETRY_WITH_CONTEXT/REQUEST_REVIEW)
→ resolve → execution decision (含 reason)
resolve 返回: {decision, reason, strategy, conflicting_tasks, ordered_tasks}
不实现 Git merge (边界)
```

## 5. P4: orchestrator 集成

```
before_task: detect → DecisionEngine.decide
  - SERIALIZE → 等待前序任务释放 (冲突文件)
  - BLOCK → 暂缓
inject_context: + reservations/changed_files/decisions
after_task: release_reservation + workspace 更新 + handoff
```

## 6. P5: 真实冲突场景 (S10-054 问题直接解决)

```
Backend T003 → main.py
Frontend T005 → main.py (同文件!)
DecisionEngine → SERIALIZE (T003 先执行, T005 等待)
T003 完成 → release → workspace 更新
T005 获得最新 Context → 继续
→ 执行前避免冲突, 不依赖 Repair Loop
```

## 7. P6: 可解释性

```
所有决策含 reason:
  {decision: SERIALIZE, reason: "backend-1 and frontend-1 both require write access to main.py",
   conflicting_tasks: [T003, T005], strategy: "execute T003 first"}
资产: handoff_decisions.json / workspace_locks.json / conflict_resolution.json
```

## 8. 模块计划

```
新增: session/decision.py (HandoffDecisionEngine)
修改: session/workspace.py (reservation) / session/conflicts.py (execution decision)
      / session/orchestrator.py (DecisionEngine 集成)
新增: tests/console/test_session_team_decision.py (>=100)
文档: S10-059-gap-analysis.md + S10-059-team-decision.md
```

## 9. 边界 (严格限制)

- 不做: PyPI/GitHub marketing/UI/SaaS/账号/Billing/云部署/多租户/Git merge/DAG 并行/Reviewer 大系统
- 核心: 防止 Agent Team 因共享文件修改产生确定性失败

---

> 设计完毕 | DecisionEngine + Workspace Isolation + Conflict→Decision + 真实冲突场景
