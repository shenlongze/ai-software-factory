# 05 — LEGACY ISOLATION (P0-F1, 2026-09-04)

> F1 后 legacy 边界确认 — 不迁移、不重连、只读保留

---

## 1. Legacy/Adapter 状态 (F1 未触碰)

| 对象 | 分类 (F0) | F1 后状态 | 证据 |
|---|---|---|---|
| task-e1-* (M3 orchestrator) | LEGACY | 未改; 未接入 backlog | orchestrator.py 未动; audit 8/18 只读 |
| EXR-* (requests.json 86) | ADAPTER/LEGACY | 未提升; 未加新入口 | exec/store.py 未改 canonical 语义; backlog_sweeper 独立路径保留 |
| TASK-GW-* (external_tasks 9) | ADAPTER | 保留 (gateway 内部控制面) | gateway registry 未迁移 |
| execution_plan T-* | HISTORICAL | 未动 (STEP10 D-9) | — |
| 历史 EXS (无锚) | 旧数据 | 保留空锚, 不猜测回填 | test_exs_backward_compatible |
| 旧 exec_ref (EXR/bridge:) | legacy 写点 | CLI bridge 保留; T-9 EXR 回退 | §03 |
| session_exec (6 E2E) | ORCHESTRATION STATE | 未清理 (用户决策) | — |
| factory.db events | EVENT MIRROR | 未动 | — |

## 2. 隔离保证 (测试)

- task-e1-*/EXR-*/TASK-GW-* 不符合 canonical run-*/EXS-* 格式 (test_legacy_ids_not_valid_task_run_anchors)
- 旧 EXS/ExecutionResult JSON 反序列化默认空锚 (兼容) (test_execution_result_model_old_data_compatible)
- 未迁移任何历史数据 (本 Sprint 零数据写; 仅测试 tmp 工作区)

## 3. 新写方向 (canonical)

```
新 TaskRun 创建:      create_node_run(..., task_id=TASK-*)   → run-*
新 EXS 记录:          record_invocation(..., task_id, task_run_id)  → EXS-* (带锚)
新 Task.exec_ref:     EXS-* (agent_loop; 非 TASK-GW/EXR)
新 Node:              "task-execution" (共享模板, chain 首次自动注册)
```

## 4. 禁止事项确认 (F1 全程遵守)

- ✅ 未批量迁移旧 execution_records / audit / EXR / task-e1-*
- ✅ 未重建 factory.db
- ✅ 未给旧 task-e1-* 重新绑定 TASK-*
- ✅ 未改变 Task state machine (八态 transition 未动)
- ✅ 未实现 Verification / Artifact / Evidence / Release / Learning
- ✅ 未改 WebUI / CLI 新功能 / orchestrator M3
