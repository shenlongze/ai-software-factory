# ORCHESTRATION STATE / RECOVERY / CANCELLATION AUDIT

> 日期: 2026-09-01 | 基线: 914bc341 + 2da49ecc | 状态: READ-ONLY (P2 审计)

## 1. 状态机盘点

### Task (backlog SSOT, 七态)

```
todo → ready → in_progress → {review → done} | {failed}
blocked = 依赖失败传播 (仅 ExecState 派生, 不落 backlog — P2-3)
failed → ready (重试, transition 支持) | blocked
cancelled: 不存在
[org/management.py] TaskStatus L81-95 + TASK_TRANSITIONS L334-342
```

### Plan (PendingPlanStore SSOT)

```
pending → executing (execute_plan 消费) → [completed/failed 无自动闭环 — P2-4]
[agent_loop.py] update_status L915 (executing/failed only)
[agent_loop.py] 幂等检查 L890 (executing/completed/failed)
```

### ExecState (投影)

```
running/done/failed/blocked (调度态; todo 初始)
[exec_state.py] next L110-160
cancelled: 不存在; stop 不写 ExecState (grep 0)
```

### Run (gateway registry)

```
running → done/failed (registry 记录, 含 exec_ref)
[gateway.py] reg.update L144/L195
```

## 2. P2-1 Cancellation(确认)

```
CURRENT: Stop (cancel API) → 停止 run_agent_native → 不写 ExecState/backlog
ExecState 任务 running 残留; Task SSOT in_progress 残留 (start_task_exec 已写)
restart → ExecState.next 只选 todo → running 任务被跳过 → 永久卡住
Event/Audit: Stop 无独立事件
RISK: 状态混淆 (running 但实际已停); 重启卡住; 无 retry 入口
```

## 3. P2-2 Running Recovery(确认)

```
CURRENT: 进程 crash → ExecState running 残留; Task in_progress 残留
Run registry running 残留
next 只选 todo → 卡住; 无恢复/孤儿清理逻辑
执行事实 UNKNOWN (无法区分"已完成但未回写" vs "确实没完成")
不应伪装 FAILED (执行事实未知 ≠ 失败)
```

## 4. P2-3 Blocked 回写(确认)

```
CURRENT: B blocked 仅 ExecState; backlog B 保持 todo
restart/新 session: ExecState 持久化保留 blocked (可恢复)
但 backlog 无 blocked 事实 (查询/UI/审计缺失)
A retry 成功 → ExecState 重算 (B 依赖 done → ready) — 无自动解除逻辑
blocked = 派生状态 (设计一致, 但投影丢失风险: ExecState 删除后不可从 backlog 重建 blocked)
```

## 5. P2-4 Plan Completion(确认)

```
CURRENT: Plan 永不自动 completed (无 Task 全 done → completed 回写)
Task 全 DONE / 含 FAILED / 含 BLOCKED → Plan 均保持 executing
restart 后 Plan 状态 = 持久化值 (executing)
GAP: Plan 层级状态未与 Task 状态聚合
```

## 6. P2-5 Retry(确认)

```
CURRENT: FAILED → READY 转换受支持 (transition), 但 chain_next 只选 todo →
failed 任务不自动重试; retry 需人工改状态
retry 会产生新 Run (gateway 新 exec_ref); 原 Run 保留 (registry)
dependency 重算: ExecState.next 基于当前 done/failed → 自动
plan 不受影响 (plan_id 幂等保持)
```

## 7. P2-6 Idempotency(确认)

```
plan_id: execute_plan 幂等 (85c237f0) ✅
task_id: finish_task_exec 幂等 (done/failed 不重复转换) ✅
chain_next: 只推进下一个 todo, 无重复执行 ✅
run_id/exec_ref: gateway 每执行生成新 id ✅
cancel/restart: 无幂等语义 (状态缺失)
```

## 8. P2-7 Crash Consistency(确认)

```
exec_state._save_json: 非原子 (write_text 覆盖, 崩溃可能半写 — 风险低)
backlog/plan: 原子写 (tmp+replace, G2 已实现) ✅
Run registry: 非原子 (同 exec_state)
事实已发生但状态未记录: 可能 (crash 在 gateway 完成与回写之间)
状态已记录但事实未发生: 低 (回写在执行后)
AI 回复不作为事实 (Execution Truth 冻结) ✅
```

## 9. 状态冲突裁决

```
Task (backlog) = 最高权威 (事实)
ExecState = 投影 (冲突时以 backlog 为准; chain_next 回写保持同步)
Run = 执行事实 (task_id/exec_ref 关联)
Event/Audit = 记录
```

## 10. 统一状态矩阵

| Object | State | Type | SSOT | Writer | Recovery | Retry |
| --- | --- | --- | --- | --- | --- | --- |
| Plan | pending/executing | Fact | PendingPlanStore | plan_development/update_status | 持久化 | 否 |
| Plan | completed | **缺失** | — | — | — | — |
| Task | todo/ready/in_progress/review/done/failed | Fact | backlog | transition/finish_task_exec | 持久化 | failed→ready |
| Task | blocked | **投影 only** | — | ExecState | 投影丢失风险 | 否 |
| Task | cancelled | **不存在** | — | — | — | — |
| ExecState | running/done/failed/blocked | Projection | session_exec | next | 持久化; running 卡住 | 否 |
| Run | running/done/failed | Fact | gateway registry | gateway | registry; crash UNKNOWN | 新 Run |

## 11. 结论

```
P0: 0
P1: 0
P2 (排序):
  ① cancelled 缺失 + Stop 不写 ExecState (状态混淆/重启卡住)
  ② running 恢复/孤儿清理缺失 (crash 后 UNKNOWN, 无 retry 入口)
  ③ blocked 不回写 backlog (投影丢失风险)
  ④ Plan completed 自动闭环缺失
P3: exec_state/registry 非原子写 (风险低)
UNKNOWN: crash 时执行事实 (gateway 完成与回写之间)
```

## 12. Architecture Judgment

```
状态层级: Task(事实) > Run(执行事实) > ExecState(投影) — 已冻结
核心缺口: cancelled / running 恢复 / blocked 回写 / Plan 闭环 —
全部属于"执行状态模型完整性", 真并行前置
```

## 13. Recommended Next Step

```
P2 修复序列 (等 FIX 指令):
① Stop → 写 ExecState cancelled + Task 状态 (或 cancelled 枚举)
② running 恢复: restart 时 UNKNOWN → 人工确认 or 自动 todo/重试
③ blocked 回写 backlog (依赖传播时)
④ Plan completed: 全 Task done → completed; 含 failed → failed
```
