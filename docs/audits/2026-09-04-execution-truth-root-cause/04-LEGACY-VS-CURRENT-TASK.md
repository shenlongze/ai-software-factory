# 04 — LEGACY vs CURRENT TASK (Execution Truth Root Cause)

> 取证日期: 2026-09-04 | READ ONLY | 代码 + 数据 ID 级判定

---

## 1. 两套 Task 判定

| 维度 | Current Backlog Task | Legacy M3 Orchestrator Task |
|---|---|---|
| ID | TASK-<hex10> | task-e1-core / task-client-ui / T001 / T002 |
| Model | org.management.Task (management.py:141-166) | orchestrator.py 内部 task dict |
| Storage | workspace/projects/*/management/backlog/task.json | execution_state.json / memory (projects/*/) |
| SSOT | 是 (org 域唯一 Task SSOT) | 否 |
| Producer | service.create_task (service.py:3969) | orchestrator.execute_project (M3) |
| 审计 | TASK_CREATED (service.py:4035) | TASK_STARTED/ARTIFACT_CREATED/TASK_COMPLETED (orchestrator 2174/2869/3223) |
| 消费 | WebUI/chain/plan_id 引用 (53) | 历史执行记录 |
| 活跃? | **当前生产 (Web 主链建任务)** | **CLI 路径仍可达但属旧体系; 最近事件 8/18** |

## 2. 关键证据

1. **orchestrator.py:3223** TASK_STARTED 的 project_id = `project_dir.name` → 数字目录名 (1787033426),
   task_id = M3 内部 id (task-e1-core)。这就是 audit 中 8/18 事件的来源。
2. **audit ID 级抽样** (03 文件 §3): task-e1-* 有完整 STARTED→COMPLETED; 当前 TASK-* 只有 CREATED, 0 STARTED/COMPLETED。
3. **cli_factory.py:8133** InteractiveSession (CLI) 仍路由 execute_project → ExecutionOrchestrator → M3。
4. **fastapi_adapter.py:7040/7850** Web 主链 run_agent_native → chain (session_exec/TASK-GW), 不经过 orchestrator M3。
5. **ai-factory-self backlog 156 tasks**: 无 plan_id / 无 exec_ref (历史数据), 而 E2E 项目 (P-b0adfaa6/orch-e2e 等) 53 tasks 带 plan_id — 说明 plan→task 链只在 S34 后的 E2E 验证中出现, 未回流自身项目。

## 3. 判定

- **Current canonical Task = backlog TASK-*** (org.management.Task): 有独立 model + SSOT 文件 + CRUD API + 创建审计。
- **Legacy runtime = orchestrator M3 (task-e1-* / T001-005)**: 8/18 后无新事件; 代码仍被 CLI 路径引用, 但 Web 生产主链不经过它。其 audit 事件链 (STARTED/COMPLETED) 是历史证据, **不应硬接到当前 TASK-* canonical chain**。
- **边界建议**: 标记 M3 orchestrator 为 historical (CLI execute_project 若保留需另立迁移), 不得让 FX-01 试图把 task-e1-* audit 或 T001 EXR 记录映射为当前 TASK-* 的执行证据。

## 4. 涉及代码清单 (历史/保留)

| 文件 | 函数 | 说明 |
|---|---|---|
| factory-console/session/orchestrator.py | execute_project / _run_queue / _execute_m3* / emit | M3 旧执行 (TASK_STARTED/COMPLETED producer) |
| factory-console/session/actions.py | execute_project (1645) / execute_task (1355) | CLI 入口 |
| factory-console/session/agent_loop.py | execute_plan (434) / chain_start (1409) / chain_next (1530) | 当前 Web 主链 (backlog + session_exec) |
| factory-console/external_executor/* | gateway/executor/task_registry | 委派控制面 (TASK-GW/EXS) |
| factory-console/service.py | start_task_exec (4378) / finish_task_exec (4469) / create_task (3969) | backlog 执行绑定/回写 API |
