# 05 — IDEMPOTENCY & RECOVERY (P0-F2, 2026-09-04)

---

## 1. Idempotency (F2 §9 P0)

### 实现保证

- `finalize_node_run`: 幂等入口。终态 (COMPLETED/FAILED) → 直接返回现状
  (不追加 history / 不重复转换 / 不逆转)。见 node_runtime.py finalize_node_run.
- `finish_task_exec` (service): 已是目标态 → 仅追加审计 (不重复转换)。
- gateway record_invocation: 每次 attempt append (EXS 不覆盖) — 幂等天然 (attempts 历史)。

### 重复触发场景 → 结果

| 场景 | 结果 |
|---|---|
| complete(EXS); complete(EXS) | 终态一致, history 不重复 (E2E-3: 4 次调用) |
| 成功后误调 success=False | 终态不被逆转 (COMPLETED 保持) |
| 失败后误调 success=True | 终态不被逆转 (FAILED 保持) |
| process restart 后重复处理 | finalize 看 run.state, 终态已定 → 幂等 |
| 重复创建 TaskRun | create_node_run 每次新 run (同 Task 多 run 合法) — 非同一 run 重复 |

## 2. Recovery (F2 §10)

### 语义区分

```
Execution Attempt → EXS FAILED → TaskRun FAILED → (retry 决策) → 新 TaskRun → 新 EXS → 终态
```
- FAILED TaskRun ≠ Task COMPLETED (不混)
- 最终 Task 状态 = 最终 canonical TaskRun outcome (E2E-4: attempt2 成功 → done + exec_ref=最终 EXS)
- 复用既有 failed→ready→in_progress 重试路径 (TASK_TRANSITIONS: FAILED→READY→IN_PROGRESS)

### recover (chain_next)

`_run_status` 三级证据 (F2 Gap-3 修复):
1. **NodeRun (run-*)**: state COMPLETED→done / FAILED→failed (canonical TaskRun)
2. **EXS**: result success→done / failed→failed (canonical execution result)
3. **TASK-GW registry**: done/failed (legacy 兼容)
UNKNOWN → todo 重排队 (不伪造; ExecState.recover 既有语义)

### 边界 (未做, F2 §3)

- 不自动 Replan (失败不自动新 Plan)
- 不自动重试循环 (gateway max_retry 已有; 人工/决策层发起新 attempt)
- 不把 FAILED→retry 与 FAILED→COMPLETED 混为一谈
