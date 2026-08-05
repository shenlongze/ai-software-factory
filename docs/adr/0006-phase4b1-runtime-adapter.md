# ADR-0006: Phase 4B-1 Runtime Adapter Interface — 事件扩展、存储布局与集成边界

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase4b1-status.md` · `docs/architecture.md` §7.1 · `docs/adr/0002-phase2-cli-events-layout.md` · `docs/adr/0001-eventtype-and-events-schema.md`

## 背景

Phase 4B-1 为 Workflow Engine 与具体 Agent Runtime 之间建立隔离层: 新模块
`factory-core/runtime/` (ExecutionRequest/ExecutionResult + RuntimeAdapter 抽象接口 +
RuntimeRegistry + RuntimeStore JSON 持久化), WorkflowEngine 新增 `execute_step`
(创建 pending execution, **不自动调用 Runtime**), CLI 新增 `runtime add/list` 与
`execution list`, 事件流新增 `runtime.*` / `execution.*`。本阶段**无具体 Runtime 实现**。

落地时有六处设计张力需明确:

1. **事件词汇**: 任务指令列出 6 个事件 (runtime.registered/removed + execution.created/
   started/completed/failed); ADR-0002 铁律"所有 CLI 行为必须产生 Event"要求读命令
   (`runtime list` / `execution list`) 也有事件 — 指令清单未列 viewed 类事件。
2. **ExecutionRequest 状态字段**: 指令字段清单 (id/task_id/workflow_id/step_id/agent_id/
   runtime_id/input/created_at) 不含 status, 但"创建 pending execution (状态 PENDING)"与
   execution.created 载荷均需请求级状态。
3. **execution.started/completed/failed 发射点**: 本阶段无具体 Runtime, 没有任何代码
   "真正执行" — 这三个事件在 4B-1 没有自然发射位置。
4. **执行记录归属**: 指令要求 `.factory/runtimes/runtimes.json` + executions 记录;
   ExecutionResult (含 output/error) 的持久化位置未明确。
5. **目录布局**: cli/context.py 的 `_SUBDIRS` 不含 runtimes/ (文件范围禁止修改 context.py)。
6. **agent_id 解析**: 指令要求 execute_step "从 AgentRegistry 取 agent_id 或留空" —
   解析规则未明确; resolve_runtime_id 辅助放 Adapter 还是 Registry 未明确。

## 决策

1. **事件按任务指令增量扩展 + 补 viewed 事件** (沿 ADR-0001 扩展路径: 加枚举成员即可,
   不改表结构/API): `runtime.registered / runtime.removed / execution.created /
   execution.started / execution.completed / execution.failed`, 外加
   `runtime.viewed / execution.viewed` (读命令事件, 满足 ADR-0002 铁律 — 与 agent/skill/
   workflow 的 viewed 事件同构; 若不补, 这两个读命令将是全项目唯一不发事件的命令)。
   `execution.started/completed/failed` 为枚举成员 + 可经 EventLogger 记录 (模型/存储层
   已就绪), **发射点落在 4B-2 派发层** (无 Runtime 即无执行, 本阶段不制造假发射点)。
2. **ExecutionRequest 补 status 字段 (默认 PENDING)**: 指令字段清单为"必含"而非"仅含";
   无请求级状态则"pending execution"与事件载荷的 status 无法表达。状态推进
   (PENDING→RUNNING→SUCCESS/FAILED) 走 RuntimeStore.save_execution upsert;
   ExecutionResult.status 校验强制终态 (SUCCESS/FAILED), 拒绝中间态。
3. **单文件三节存储** (参照 workflows/store.py 模式): `runtimes.json` =
   `{"runtimes": {id: RuntimeInfo}, "executions": {id: ExecutionRequest}, "results": {request_id: ExecutionResult}}`;
   原子写 os.replace, 损坏抛 CorruptRuntimeStoreError。results 以 **request_id** 为键
   (一次执行至多一个结果, upsert 幂等 — 完成语义天然可重入), 偏离"键 = 模型 id"惯例
   是刻意的领域选择。
4. **execute_step 的 agent_id 解析 KISS**: 只做 task.owner 精确引用解析
   (owner 命中已注册 Agent → 取其 id), 否则留空 None。按角色/技能自动分配
   (首个 AVAILABLE 等) 属 4B-2 派发层职责; WorkflowEngine 构造参数新增可选
   `runtime_store` / `agent_registry` (纯增量, 不破坏既有 API)。
5. **runtimes/ 目录不进 context.py 骨架**: 文件范围禁止修改 context.py;
   RuntimeStore 首次原子写时自动 mkdir (store._write_all 已含), `factory runtime add`
   即创建目录。init 的 dirs 列表不含 runtimes/, 后续 Phase 统一并入骨架。
6. **resolve_runtime_id 放 RuntimeRegistry 而非 Adapter**: 解析需要访问注册状态
   (显式 id 须已注册 / 首个 AVAILABLE), Adapter 无 store 依赖。语义: 显式 id
   (未注册抛 RuntimeNotFoundError) → 首个 AVAILABLE → None (无可用 Runtime,
   执行留在 PENDING)。RuntimeAdapter 抽象接口保持最小 (仅 abstract execute)。

## 后果

- EventType 纯增量扩展 8 成员; 事件库无 schema 变更, 既有测试断言不受影响
  (既有测试只断言成员存在, 不断言总数)。
- 新模块 factory-core/runtime/ 4 文件 + __init__; WorkflowEngine 新增
  execute_step (前置: run RUNNING + 步骤为当前步骤 + 非终态; 产物: PENDING
  ExecutionRequest 落库 + execution.created, 步骤状态不变)。
- CLI 新增 `factory runtime add|list` / `factory execution list`, 支持 `--json`;
  退出码沿用 cli-design §5 (重复注册=1, 状态解析失败=2, argparse 用法=2)。
  `runtime add --type` 默认 "agent" (本阶段唯一类型)。
- 风险: runtimes.json 整文件读写, 单进程假设下无并发问题 (同 workflows.json);
  若未来多进程写入需文件锁 (Phase 4 议题, 与 ADR-0004 同款风险)。
- 后续 Phase (4B-2): 具体 Runtime (hermes/mock) + 派发层 — resolve_runtime_id →
  execution.started → adapter.execute → execution.completed/failed → ExecutionResult
  落 results 节; agent 自动分配与 runtime_id 填充在派发层落地。
