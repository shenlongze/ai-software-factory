# 00 — F1 COMPLETION (2026-09-04)

> Sprint: P0-F1 Execution Record Normalization | Status: COMPLETE
> 依据: P0-F0 Canonical Identity & Ownership Contract Freeze (人工批准)
> 前置审计: docs/audits/2026-09-04-execution-truth-f1/00-PRE-IMPLEMENTATION-AUDIT.md
> Bridge 决策: 方案 A (chain 委派自动注册共享 Node + create_node_run(task_id) → run-* 锚,
> gateway 透传 task_id/task_run_id → EXS) — 用户 2026-09-04 批准

---

## 1. 完成内容

### Identity Relations (目标状态达成)

```
Task(TASK-*)
    │ task_id (显式持久化)
    ▼
TaskRun(run-*)  ← create_node_run(task_id=TASK-*) — backlog 委派时创建
    │ task_run_id (显式持久化)
    ▼
EXS(EXS-*)      ← record_invocation(task_id, task_run_id) — canonical 结果记录

Task.exec_ref = EXS-* (唯一语义; 生产链不再写 TASK-GW)
```

### 代码改动 (7 生产文件, +118/-18)

| 文件 | 改动 | F0 对齐 |
|---|---|---|
| factory-console/node_runtime.py | create_node_run 增 task_id 参数; run 记录 task_id 字段 | TaskRun.task_id → Task |
| factory-exec/exec/models.py | ExecutionResult 增 task_id/task_run_id (默认空, 旧数据兼容) | EXS.task_run_id → TaskRun |
| factory-console/external_executor/executor.py | record_invocation 增 task_id/task_run_id 写入 EXS 记录 | EXS 锚定 |
| factory-console/external_executor/gateway.py | gateway_execute 增 task_id/task_run_id 透传 | Task→TaskRun→EXS 创建链 |
| factory-console/session/agent_loop.py | _chain_task_run helper (共享 Node "task-execution" 自动注册 + create_node_run); 两处 _exec_fn (chain_next + auto worker): 先锚 run → gateway 透传 → exec_ref=result_id (EXS); finish_task_exec exec_ref 用 task 副本 EXS | 生产主链创建阶段形成关系 + exec_ref 语义 |
| factory-org/org/management.py | Task model 注释: exec_ref=EXS-* (F0 语义, 废除 EXR 描述) | 文档对齐 |
| factory-console/web/backend/fastapi_adapter.py | T-9 溯源: exec_ref 先按 EXS 直查 (canonical); EXR 查询降 legacy 回退 | 读端对齐 exec_ref=EXS |

### 未产生平行 SSOT

- TaskRun: 复用 NodeRun (run-*), 未新建 TaskRunModel/ExecutionRun
- Execution: 复用 EXS (execution_records.json), 未新建 ExecutionRecordV2
- NodeRun 仍是唯一 run 事实; EXS 仍是唯一结果记录

---

## 2. 验收对照

| F1 §12 验收 | 结果 |
|---|---|
| Task=TASK-* / TaskRun=run-* / EXS=EXS-* | ✅ |
| TaskRun.task_id → Task | ✅ (create_node_run task_id; run 持久化) |
| EXS.task_run_id → TaskRun | ✅ (record_invocation + ExecutionResult) |
| Task.exec_ref → EXS | ✅ (agent_loop 两处写 result_id; T-9 读 EXS) |
| 无平行 TaskRun/Execution SSOT | ✅ |
| Legacy 隔离 (EXR/TASK-GW/task-e1-* 不作 canonical) | ✅ (未迁移/未提升; T-9 EXR=legacy 回退) |
| Persistence 保存关系 | ✅ (nodes/runs/*.json + exec/execution_records.json) |
| 新测试通过 | ✅ 16/16 (tests/console/test_p0_f1_identity_relations.py) |
| 回归 | ✅ org+exec 2228 passed; node/gateway/trace 52 passed; 旧 exec_ref 测试 53 passed |

---

## 3. 遗留 (明确留给 F2/F3/F4, 非 F1 缺陷)

1. **session_exec 收敛 / Task 状态自动完成** → F2 (本 Sprint 未触碰 convergence)
2. **NodeRun 状态推进** (create 后 PENDING; 执行完成 → COMPLETED/FAILED 由 F2 TaskRun 生命周期驱动) — F1 只建锚
3. **Verification SSOT** → F3 (gateway verify dict 未动)
4. **Artifact/Evidence 链路** → F4 (exec ART-* 未动)
5. **EXR 提升 / execution_records 与 results.json 双存储合并** → 未做 (历史存储保留; canonical 写入点在 record_invocation)
6. **backlog_sweeper 审批路径** (EXR/EXS 手工构造) → 未改 (独立工具链, 后续按 F1 锚定规范对齐)
7. **CLI bridge (cli_factory 2598/2624)** exec_ref=bridge:/EXR → 保留 (legacy adapter, 输出仍可被 T-9 EXR 回退追溯; 不迁移)

---

## 4. 已知限制 (诚实声明)

- 现存历史 EXS 记录无 task_id/task_run_id → 不猜测回填 (F0: 旧数据 task_run_id=null 允许)
- 现存 6 个 E2E session_exec 未清理/未收敛 → 用户决策项 (非 F1 范围)
- 共享 Node "task-execution" 在 chain 委派首次运行时自动注册; 该 Node 是模板 (多 TaskRun 复用合法)
- agent_loop 的 11 个既有测试失败为**预先存在** (git stash 验证, 与 F1 无关)
