# 03 — WRITEBACK CONTRACT (P0-F2, 2026-09-04)

> 完成传播契约 — EXS → TaskRun → Task

---

## 1. Contract (冻结)

```
Success:
  EXS.result = success
    → finalize_node_run(success=True) → NodeRun COMPLETED
    → finish_task_exec(success=True)  → Task done
    → Task.exec_ref = EXS (EXS 确定后才写)

Failure:
  EXS.result = failed (或无执行器 → 无 EXS)
    → finalize_node_run(success=False) → NodeRun FAILED
    → finish_task_exec(success=False)  → Task failed
    → Task.exec_ref = EXS (若 EXS 存在; 无 EXS → 空)

Cancelled:
  → finish_task_exec(cancelled=True) → Task cancelled (既有路径, 未改)
```

## 2. exec_ref Contract (F2 §7)

- Task.exec_ref 只在 EXS 确定后写入 (gateway 返回 result_id 后)
- 禁止: exec_ref = run-* / EXR-* / TASK-GW-* / session_exec id
- 失败路径也回传 EXS (Gap-2 修复): _exec_fn 失败 return 带 exec_ref=_exs
- 无 EXS 场景 (无执行器/权限拒绝) → exec_ref 空 (诚实, 不伪造)

## 3. 幂等 (F2 §9)

- finalize_node_run: 终态 (COMPLETED/FAILED) → 返回现状, 不重复转换, 不可逆
- finish_task_exec: 已是目标态 → 仅追加审计, 不重复转换
- E2E-3 实证: 4 次 finalize (含 success=False) → 终态 COMPLETED 不变, EXS 记录=1

## 4. 状态名遵循现有 canonical enum

- Task: done (成功) / failed / cancelled (org.management.TaskStatus, 无 COMPLETED 字面 — F2 §6 遵循现有 enum)
- NodeRun: COMPLETED / FAILED (NODERUN_STATES)
