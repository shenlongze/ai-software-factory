# 07 — PRODUCTION → EXPERIENCE (P2-C CONTRACT, 2026-09-06)

## 1. 单向派生 (冻结)

```
TASK → TaskRun → EXS → art → ver → EVD
  (P0 canonical, 不依赖 exp)
        ↓ finalize 终态后 (Trigger-1)
ExperienceBridge.record(task_run_id, exs_id, source="execution",
                        source_id=f"{run_id}:{exs_id}", ...)
        ↓
exp-* (task_run_id + exs_id anchor)
```

## 2. 失败/恢复/修复语义

| 场景 | exp 记录 |
|---|---|
| EXS SUCCESS + ver PASS | 1 条 (SUCCESS_PATTERN, success=true) |
| EXS SUCCESS + ver FAIL | 1 条 (FAILURE_PATTERN, success=false) |
| EXS FAILED | 1 条 (FAILURE_PATTERN, success=false) |
| Recovery (TaskRun-2 成功) | TaskRun-2 自身 1 条 (新 run 新 exp); TaskRun-1 的 FAIL exp 保留 (历史 attempt 可追踪) |
| Repair (ver FAIL→PASS) | 修复后同一 finalize 的 PASS 结果为准 (repair 细节入 detail 不另建 exp) |

**不自动把失败记成功** — success 字段 = ver/EXS 真实结果 (P0 语义)。

## 3. 不记录中间态

每次 finalize 终态恰好 1 条 (幂等键 (source, source_id) = (execution, run:exs))。
