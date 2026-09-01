# AI Factory — Orchestration Contract(编排契约,冻结版 v2)

> 基线: 92cc058e → b7802e61 → 7c5d0b92 → 03da51aa → 45810d64 → 85c237f0 → 914bc341
> 状态: FREEZED (证据: test_planning_orchestration + 确定性 E2E + 状态写者代码审计)
> v2: 补充 State/Fact Source 矩阵 + 多状态源风险 + 证据定位

## 1. Purpose

冻结 Planning → DAG → Scheduling → Execution 的生产语义(事实源/状态源/派生状态/恢复),作为 SQLite / 多 Agent / 真并行演进必须遵守的宪法。

## 2. Scope

会话生产链(Idea → Plan → Task → ExecState → chain_next);orchestrator M3 为历史路径(§21)。

## 3. State / Fact Source Matrix(核心)

| Domain | Object | 类型 | SSOT | 写者 | 落盘 | History | Event | Projection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Management | Task | 事实 | backlog/task.json | create_task/transition_task/update_task/finish_task_exec | ✅ | task.history | TASK_CREATED 等 | WebUI |
| Management | Task.dependency | 事实 | backlog (同文件) | create_task/update_task | ✅ | — | — | DAG |
| Planning | Plan | 事实 | session_plans.json (PendingPlanStore) | plan_development/update_status | ✅ | — | — | 计划卡 |
| Orchestration | ExecState | **投影** | session_exec/{sid}.json | chain_start/execute_plan 初始化 + ExecState.next | ✅(可重建) | — | — | 执行卡 |
| Execution | Run | 事实 | session.run_ids + gateway task_id (exec_ref) | gateway_execute/chain_start | ✅ | — | 会话 Run 卡 | — |
| Governance | Event | 事实 | audit/audit_events.json | AuditEmitter | ✅ | — | SSOT | — |
| Governance | Audit | 记录 | audit/audit_events.json | audit | ✅ | — | — | — |
| Session | Session | 事实 | console_sessions.json | SessionStore | ✅ | — | — | — |
| Project | Project | 事实 | org/projects.json | ProjectStore/service | ✅ | project.history | — | workspace index |

## 4. Task State Contract(谁写)

| 状态 | Task SSOT (backlog) | ExecState (投影) | 写者 |
| --- | --- | --- | --- |
| todo | ✅ | ✅ | create_task / chain_start |
| running | ❌ (无) | ✅ | ExecState.next (exec_state.py:134) |
| done | ✅ | ✅ | finish_task_exec (agent_loop.py:1547) / ExecState.next:143 |
| failed | ✅ | ✅ | finish_task_exec / ExecState.next:143 |
| blocked | ❌ (**只在 ExecState**) | ✅ | ExecState.next (依赖失败传播) |
| cancelled | ❌ (不存在) | ❌ | — |

**风险**: blocked 只存在于 ExecState(不回写 backlog)。backlog 的 blocked 统计(project_tasks)来自 status 字段,若任务从未被标 blocked 则统计缺失;ExecState 持久化保留 blocked,重启可恢复,但 backlog 无 blocked 事实。

## 5. Dependency Contract

```
dependency = execution hard constraint (backlog, task id 列表)
- 不存在/删除: resolve 失败 → [] (失败安全)
- cycle/自引用: validate_dependency 拒绝 (execute_plan)
- 失败传播: 依赖 failed → 直接下游 blocked → 间接经依赖链 (ExecState.next)
- blocked 传播: blocked 任务作依赖 → 下游 waiting (无独立 blocked 传播)
- cancelled: 无 (状态不存在)
```

## 6. Ready Contract(派生,不持久)

```
Ready(T) = status == todo AND all(dep in done_ids)   [exec_state.py next]
Ready 是 Scheduler 计算结果, 不是 Task 持久状态
A done → Ready={B,C}; B done → {C}; C done → {D} (汇聚判定全 done)
Ready-set 一次只执行一个 (生产串行)
```

## 7. Waiting Contract

```
todo 且依赖未完成 → 不执行 (派生, 不持久)
```

## 8. Running Contract

```
ExecState.next 选中 → running (exec_state.py:134, 仅投影)
backlog 不写 running (Task SSOT 无 running 事实)
```

## 9. Done / Failed Contract

```
exec_fn ok → done; fail → failed (ExecState) + finish_task_exec 回写 backlog
(agent_loop.py:1547; 事实写回 Task SSOT)
```

## 10. Blocked Contract

```
依赖 failed → blocked (ExecState only, 不回写 backlog)
孤立分支 (不依赖失败任务) 继续执行
CURRENT GAP: backlog 无 blocked 事实
```

## 11. Cancelled Contract

```
不存在。CURRENT: Stop 后 ExecState running 残留 (P2)
GAP: 无 cancelled 状态; RISK: 重启后 running 任务被跳过 (next 只选 todo)
```

## 12. Scheduling Contract

```
Hard Constraint: dependency (Ready 定义)
Tie-breaker: ExecState.tasks 列表顺序 (≈ plan order)
Execution Mode: 单任务串行
```

## 13. Failure Propagation

```
A failed → 直接依赖 A 的 B blocked → D (依赖 B) blocked; C (孤立) 继续
(证据: test_planning_orchestration.test_failure_propagates_blocked)
```

## 14. Restart / Recovery

```
ExecState 持久化: done 保留不重复, todo 重算 Ready, waiting 保持
running 任务重启 → 跳过 (卡住, 需人工) — P2
ExecState 损坏 → load 空 → chain_start 重建 (可重建)
dependency 来源唯一 = backlog SSOT; 无第二份 Task 状态事实 (ExecState 是投影)
```

## 15. Stop / Cancellation

```
CURRENT: cancel API 停 run, 不写 ExecState (45810d64 前端修复保持)
GAP: running 残留 + 无 cancelled; RISK: 状态混淆/重启卡住
```

## 16. Idempotency

```
plan_id 幂等: 已消费 → 拒绝重复批准 (85c237f0)
done/failed/blocked/running: next 只选 todo → 不重复执行
chain_next 重复调用 → 推进下一个 (无副作用)
```

## 17. DAG Boundary

```
TaskDependencyGraph = 分析/校验 (环检测/拓扑, execute_plan 校验 + 测试)
非事实源; DAG 可重建, 不成为第二套 Task SSOT
DAG 数据来源: backlog task.dependency (唯一)
```

## 18. ExecState Boundary

```
执行投影: backlog_id + dependency (从 backlog 读) + status (复制)
可重建; 非 Task SSOT
Task.status (backlog) 与 ExecState.task.status 冲突时 → backlog 优先
(chain_next 回写 finish_task_exec 保持同步; Stop/重启可能短暂不一致)
```

## 19. Historical execution_plan Boundary

```
orchestrator.execute_project 读 execution_plan.json (M3 历史)
会话生产链不依赖 (agent_loop 无 execute_project 工具)
双路径存在 (历史兼容), 记录不重构
```

## 20. Concurrency / Parallelism Capability

```
Ready-set: ✅ (逻辑) | Worker model: 无 (串行) | 状态写: 单任务无并发
Task locking: flock (文件级, 非任务级)
若直接并行 Ready={B,C}: 双 Agent 同 workspace/Artifact/task.json 写冲突未治理
→ 真并行前必须解决 (治理 + cancelled 状态 + worker 模型)
```

## 21. Known Gaps

```
P2: cancelled 状态缺失 (Stop 语义)
P2: blocked 不回写 backlog (Task SSOT 无 blocked 事实)
P2: 真并行未实现 (串行执行; orchestrator parallel 无生产调用)
P2: running 重启卡住
P3: execution_plan 历史双路径
```

## 22. Future Evolution Boundary

```
SQLite: 只换 Storage Adapter (Task/dependency/Plan/Run/Event/Audit 表化)
真并行: 先治理 workspace/artifact/task 并发写 + cancelled + worker 模型
多 Agent: Agent assignment 进 Task 模型
不得违反: SSOT / 幂等 / 依赖硬约束 / Ready 定义 / 执行链可重建
```

## 24. Plan Lifecycle Closure(P2-④ 冻结, 2026-09-01)

```
Plan = planning fact; 终态聚合唯一事实来源 = Task SSOT (backlog, plan_id 反查)
reconcile_plan(root, plan_id) — 幂等聚合器, chain_next 轮次后触发

Aggregation:
A. 空 Plan → completed
B. 全 DONE → completed
C. 存在非终态 (todo/ready/in_progress/review) → executing
D. 全终态 且含 FAILED → failed
E. 全终态 含 CANCELLED 无 FAILED → executing + aggregate_note
   (Plan.cancelled 不是冻结 PlanStatus 契约的一部分 — 未来单独立项)
F. FAILED → retry → DONE → completed (failed 不早退, 允许恢复)

Task terminal: done/failed/cancelled; non-terminal: todo/ready/in_progress/review
不参与聚合: BLOCKED/WAITING/READY-derived/ExecState/DAG/WebUI/execution_plan.json
幂等: 状态不变不写; completed 不回落; 不创建 Task/Run; 不操作 ExecState
Restart: 仅凭 session_plans.json + backlog 可重算终态
```

## 25. Constitutional Rules

```
1. Task + dependency = 唯一事实源 (backlog); ExecState 是投影, backlog 优先
2. Plan ≠ Task; Plan 幂等消费
3. dependency = 硬约束, 不绕过
4. Ready = todo + 依赖全 done (派生, 不持久)
5. Ready-set ≠ 并行
6. 失败传播 = 依赖 failed → blocked; 孤立分支隔离
7. 执行链状态可重建 (ExecState 投影)
8. UI 永远是 View
9. 无执行事实不得声称成功 (Execution Truth)
10. 未来演进 (SQLite/并行/多Agent) 遵守上述契约
```

## 审计结论

```
P0: 0 | P1: 0
P2: cancelled 缺失 / blocked 不回写 / 真并行未实现 / running 重启卡住
P3: execution_plan 历史路径
UNKNOWN: 大 DAG 吞吐 / 并发写 (未启用并行)

Q1: 任务树 = DAG + dependency-aware scheduler ✅
Q2: Hard Constraint = dependency; Tie-breaker = ExecState 列表顺序;
    Execution Mode = 单任务串行
Q3: Ready-set parallelism = ✅ 逻辑; Logical = ✅ 多 Ready;
    Production concurrent = ❌ 未实现
```
