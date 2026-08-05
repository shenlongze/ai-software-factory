# ADR-0007: Phase 4B-2 Execution Dispatch Layer — 派发/执行生命周期/事件载荷/联动边界

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase4b2-status.md` · `docs/adr/0006-phase4b1-runtime-adapter.md` · `docs/architecture.md` §7.1

## 背景

Phase 4B-1 建立了隔离层 (ExecutionRequest/Result + RuntimeAdapter 抽象 + RuntimeRegistry +
RuntimeStore 三节 JSON), 并约定 `execution.started/completed/failed` 三个事件的发射点落在
**4B-2 派发层** (ADR-0006 决策 1)。本阶段落地该层: 新模块 `factory-core/execution/`
(Dispatcher/Runner/Service), 首个具体 Runtime 实现 EchoRuntimeAdapter (mock, 验证链路),
执行生命周期 (PENDING → started → execute → SUCCESS/FAILED → completed/failed),
Result 复用 RuntimeStore, Workflow 联动 (成功 step.completed / 失败 workflow.failed),
CLI `execution run/status`。**无真实 Runtime** — Echo 为唯一内置实现。

落地时有四处设计张力需明确:

1. **Dispatcher 与 Runner 的职责切分**: 谁解析 runtime / 谁调 Adapter / 谁管生命周期与事件 /
   谁做持久化 — phase4b2-status 把 dispatcher (resolve→Adapter→execute) 与 runner
   (生命周期) 列为两个类, 但没有细到事件与持久化的归属。
2. **execution.started/completed/failed 事件载荷**: ExecutionRequest 模型无 run_id 字段
   (4B-1 契约), 而 execution.created 载荷含 run_id — 后续生命周期事件是否补 run_id。
3. **内置 Echo runtime 的\"注册\"语义**: phase4b2-status 要求\"注册为内置 runtime
   (id: echo, type: mock)\" — 是自动写 RuntimeStore, 还是随包提供实现映射。
4. **Adapter 内部错误与 Workflow 联动异常的处置**: adapter.execute 抛异常时生命周期如何收尾;
   complete_step/fail_workflow 前置不满足 (run 终态/步骤未启动) 时是否阻断执行结果落盘。

## 决策

1. **Dispatcher = 纯派发, Runner = 生命周期所有者** (职责切分):
   - `ExecutionDispatcher(registry, adapters)`: `resolve_runtime_id(request)` (显式 id →
     首个 AVAILABLE → NoAvailableRuntimeError) + `dispatch(request)` (resolve → 找 Adapter
     → `adapter.execute` → 校验 `result.request_id == request.id`, 违反抛
     ExecutionDispatchError)。不持 logger/不落盘/不发事件。
   - `ExecutionRunner(store, dispatcher, logger=None, workflow_engine=None)`: 唯一的
     生命周期编排者 — 校验 PENDING → resolve → RUNNING (发 execution.started) →
     dispatch → SUCCESS/FAILED (发 execution.completed/failed) → 请求+结果落库 →
     Workflow 联动。所有事件经 EventLogger (source="execution_runner"; logger 缺省 → 纯存储)。
   - `ExecutionService(store, registry, adapters, logger, workflow_engine)`: 组合根
     (薄门面), `run()` 委托 Runner, `status()` 只读查询 (请求+结果, 不发事件 —
     CLI 层另发 execution.viewed, ADR-0002 铁律)。
2. **started/completed/failed 载荷不含 run_id**: ExecutionRequest 无 run_id 字段 (不改
   4B-1 模型契约 — 纯增量优先); run_id 已由 execution.created 事件携带, 经 execution_id
   即可关联到创建事件与 workflow_id/step_id。载荷统一为 execution_id/workflow_id/task_id/
   step_id/agent_id/runtime_id/status (+ completed/failed 附 result_id; failed 附 error),
   顶层 task_id 列从请求回填。
3. **内置 Echo runtime = \"实现随包, 身份显式注册\"**: `runtime/adapters/echo.py`
   (EchoRuntimeAdapter: input 原样 echo 到 output, SUCCESS; input["fail"] 真值 → FAILED
   供失败链路测试) + `runtime/adapters/__init__.py` 的 `BUILTIN_ADAPTERS =
   {"echo": EchoRuntimeAdapter()}` 提供 id→实现映射; **身份记录 (RuntimeInfo) 不自动写入
   RuntimeStore** — 须 `factory runtime add --id echo --type mock` 显式注册, RuntimeRegistry
   保持\"派发解析的唯一事实源\" (ADR-0006 决策 6 不变, 无隐式副作用/无幽灵 runtime)。
   派发时\"身份已注册但无实现\" → RuntimeAdapterNotFoundError (配置缺口, 显式报错)。
4. **Adapter 异常 → FAILED 结果, 联动异常 → best-effort 记录**:
   - `adapter.execute` 抛任意异常 (含 ExecutionDispatchError 契约违反): Runner 捕获并转换为
     FAILED 结果 (error = "ExceptionType: msg", 结果 id 从执行 id 派生), 正常走
     execution.failed 事件 + 失败联动 — 生命周期永不因 Adapter 内部错误中断。
   - Workflow 联动 (成功 complete_step / 失败 fail_workflow) 捕获 WorkflowEngineError,
     记录 `outcome.workflow_error`, **不影响执行终态落盘** (执行与工作流各自独立持久化;
     场景: run 已被外部置终态、步骤未启动等)。
   - 重入防护: 仅 PENDING 可执行; RUNNING/终态 → ExecutionStateError (results 1:1 键,
     不可重跑覆盖)。无可用 Runtime → NoAvailableRuntimeError, 执行保持 PENDING,
     **不产生任何事件** (未执行即无生命周期)。

## 后果

- EventType 无需新成员 (started/completed/failed/viewed 已在 4B-1 就绪) — 本阶段纯落地发射点。
- 新模块 `factory-core/execution/` 4 文件 (dispatcher/runner/service/__init__) +
  `factory-core/runtime/adapters/` 2 文件; WorkflowEngine **零改动** (complete_step /
  fail_workflow 已满足联动; execute_step 已创建 PENDING 请求并携带 workflow/step 绑定)。
- CLI: `factory execution run EXECUTION_ID` (输出 Runtime/Status/Result/联动摘要;
  退出码 7 未找到 / 1 状态冲突, 业务 FAILED 结果仍 rc=0) + `factory execution status
  EXECUTION_ID` (发 execution.viewed); 均支持 `--json`。CLI 装配内置 Adapter 于
  `_open_execution_service` (BUILTIN_ADAPTERS + registry + workflow engine 同事件库)。
- 手动冒烟链路 (Echo): `runtime add --id echo --type mock` → `workflow add/run` →
  engine.execute_step (造 PENDING 执行) → `execution run EX-001` (started→completed,
  联动 step.completed→workflow.completed) → `execution status EX-001`。
- 测试: `tests/execution/` 新增 ≥50 (Echo Adapter / Dispatcher / Runner 生命周期与事件序 /
  Workflow 联动 / Service / CLI run|status), 584 基线不回归 (已验)。
- 风险: 单进程整文件 JSON 写 (同 runtimes.json 既有); Echo 为内存实现无外部 IO —
  未来真实 Runtime 的异步/长时执行属后续 Phase (阻塞式 execute 契约不变)。
- 后续 Phase: agent 自动分配 (首个 AVAILABLE 等) 与 runtimes/ 入 context.py 骨架
  (ADR-0006 决策 5 遗留) 仍待落地。
