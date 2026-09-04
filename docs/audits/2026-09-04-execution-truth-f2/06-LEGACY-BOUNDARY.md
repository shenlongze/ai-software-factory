# 06 — LEGACY BOUNDARY (P0-F2, 2026-09-04)

---

## 1. Legacy 隔离确认 (F2 未触碰)

| 对象 | F0 分类 | F2 后 | 证据 |
|---|---|---|---|
| task-e1-* (M3) | LEGACY | 未改未接入 | orchestrator 未动 |
| EXR-* (requests) | ADAPTER/LEGACY | 未提升 | recover 仅 legacy 兜底读 |
| TASK-GW-* (registry) | ADAPTER | 保留控制面; 非 canonical | recover 第三级 legacy |
| 历史 session_exec (6 E2E) | ORCHESTRATION STATE | 未改写未收敛 (用户决策) | — |
| 历史 EXS (无锚) | 旧数据 | 保留 (未猜测回填) | F1 原则延续 |
| ~/.factory 历史数据 | — | **零迁移** | E2E 全部隔离 tmp |

## 2. 隔离保证

- E2E 用隔离 tmp 工作区; ~/.factory 未被读写 (零历史数据修改)
- 新 EXS 记录带 task_id/task_run_id; 旧记录保持空锚 (不补)
- finalize_node_run 只作用于新创建的 run-* (PENDING); 历史 run 文件不存在于 nodes/runs
- 无迁移函数 / 无批量改写 / 无删除

## 3. Canonical 边界 (F2 后新写方向)

```
新 TaskRun:  create_node_run(task_id=TASK-*) → finalize_node_run → COMPLETED/FAILED
新 EXS:      record_invocation(task_id, task_run_id)
新 Task 终态: finish_task_exec(exec_ref=EXS)
新 recover:  NodeRun → EXS → TASK-GW (legacy 仅兜底)
```
