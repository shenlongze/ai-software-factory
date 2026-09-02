# AI Factory — Orchestration Recovery Contract(冻结版)

> 基线: 92cc058e → ... → 914bc341 → 2da49ecc → P2-① CANCELLED
> 状态: FREEZED (只读审计, 等实现批准)

## 1. Fact Source / 关联现状

```
Task (backlog SSOT): 事实; status: todo/ready/in_progress/review/done/failed/cancelled
Run (ExternalTaskRegistry): 执行事实; status: running/done/failed (create L61 running)
ExecState (session_exec): 调度投影; status: todo/running/done/failed/blocked/cancelled

关联现状:
Task ↔ ExecState: backlog_id (ExecState 任务, chain_start/execute_plan 写入) ✅
ExecState ↔ Run: **缺失** — gateway 返回 task_id (Run tid) → chain_next _exec_fn
  exec_ref → st.next 只存 verify (不含 exec_ref) → 丢弃
  → chain_next 回写 exec_ref = _bid (backlog task id, 非 Run tid)
Run ↔ Task: 无反向 (registry 无 backlog task id 字段)
```

## 2. Crash Recovery 判定矩阵

| Crash 场景 | Task | ExecState | Run | Recovery |
| --- | --- | --- | --- | --- |
| 执行未开始 | todo | todo | 无 | 继续 (无需处理) |
| 已进入执行 | in_progress | running | running | 查 Run (exec_ref) → 同步 |
| Run 完成回写丢失 | in_progress | running | done | **同步 done, 不重跑** |
| Run 失败回写丢失 | in_progress | running | failed | 同步 failed |
| Run 未知/不存在 | in_progress | running | unknown | **UNKNOWN → 重排队 (标注)** |
| 用户 Stop | cancelled | cancelled | cancelled(调用方语义) | 永不自动重排 |
| 已 DONE | done | done | done | 不重复执行 |
| 已 FAILED | failed | failed | failed | 不自动重试 |
| 已 BLOCKED | (投影) | blocked | — | 保持依赖语义 |

## 3. UNKNOWN 语义

```
UNKNOWN = 系统无法证明 Run 最终结果 (registry 无该 exec_ref / 状态 running 但进程已死)
- 不伪造 DONE/FAILED/CANCELLED
- 不自动重跑: 转 todo + verify.recovery={result:"unknown"} (重新排队,
  执行链可继续 — 不永久卡死)
- 可重跑 (标注 unknown, 用户可接受重复执行风险) — 因为无 Run 证据
- 写 audit (recovery:unknown)
```

## 4. Idempotency Contract

```
recover 幂等: 只处理 status==running 任务 → 一次转换 (todo/同步)
重复调用一致; 不新建 Task/Run; CANCELLED/FAILED/DONE/BLOCKED 不动
retry: failed→ready (人工) → gateway 新 Run (新 tid) — 旧 Run 保留 (registry)
plan_id 幂等保持 (不触发 execute_plan)
```

## 5. 最小实现方案(等批准)

```
① exec_state.py:
   - next(): 任务存 exec_ref = result.get("exec_ref") (Run 关联键持久化)
   - recover(run_status_fn=None): running 任务 →
       run_status_fn(exec_ref): done → 任务 done; failed → 任务 failed
       其它/无 → todo + verify.recovery={result:"unknown"} (重排队)
       (幂等; 非 running 不动)
② agent_loop.py chain_next:
   - 开头调 st.recover(run_status_fn=registry lookup) → 再 next
   - 回写 exec_ref 用任务 exec_ref (非 _bid)
③ 测试 (10): 卡死解除 / 不伪造 DONE/FAILED / CANCELLED 保持 / FAILED 保持 /
   done 不重复 / Run done 同步不重跑 / 重复 recover 幂等 / DAG 重算 / 多次 restart
④ E2E: 设 running → 模拟 crash → load → recover → next 继续
```

## 6. 分级

```
P0: 0 | P1: 0
P2: running 卡死 (本轮) / Run-ExecState 关联键缺失 (实现①修复)
P3: Run cancelled 语义 (registry 无 cancelled — 调用方语义)
UNKNOWN: Run 已完成但无 exec_ref 记录的历史任务 (旧数据, 无证据 → 重排队标注)
```
