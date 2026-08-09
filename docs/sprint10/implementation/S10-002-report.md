# S10-002 — Factory Runtime API 实现报告

> 任务: S10-002 Factory Runtime API (workflow/timeline/SSE + RuntimeInstance 模型 + mock fallback) | 日期: 2026-08-10 | 状态: 已提交, 等验收 agent + 人工审核
> 依据: workspace-architecture.md §6 (Runtime API) + api-data-model.md §3-4 (端点/SSE 事件契约) + sprint10-backlog S10-002
> 约束达成: 只读 API + SSE; Core Workflow/Artifact/Approval 零修改; 不写 Timeline UI; mock 诚实标注 (is_mock); Core/Runtime/Desktop diff = 0; vitest/tsc/pytest 全绿

## 1. 交付摘要

| 项 | 结果 |
|---|---|
| 后端端点 | `GET /api/projects/{id}/workflow` + `GET /api/workflows/{id}/stages` + `GET /api/projects/{id}/timeline` + `GET /api/events/stream` (SSE) — Adapter 薄层, 路由函数无 Web 依赖 |
| 前端 client | `api.projectWorkflow / workflowStages / projectTimeline` (只读 GET) + `runtimeClient` (getWorkflow/getTimeline/subscribeEvents) |
| SSE | 7 类事件 (stage.started / stage.completed / artifact.created / approval.required / error / runtime.created / runtime.status.changed); since_seq 断点续推; 断线重连 + isMock 检测 |
| RuntimeInstance 模型 | 后端 models.py + 前端 types.ts (id/project_id/type/status/artifact_id/url/session/created_at) — 只建模型, 不实现 Browser/Terminal (S10-004) |
| mock fallback | workflow/timeline 无后端 → is_mock=true 演示数据 (诚实标注); SSE 无事件库 → 单条 error (mock=true) 后关闭; 项目不存在 → 404 (mock 不兜底不存在) |
| 测试 | pytest 6456 + 30 = **6486 全绿** / vitest **187 全绿** (177 基线 + 10 新) / tsc 零错 |
| 冻结 | git diff factory-core/ factory-runtime/ desktop/ = **0**; 未写 Timeline UI; 未实现 Browser |

## 2. 端点清单 (S10-002 Runtime API)

| 端点 | 方法 | 数据源 | 说明 |
|---|---|---|---|
| `/api/projects/{id}/workflow` | GET | org workflow + stages | 项目工作流详情 (8 阶段链/template/统计); 项目存在但无运行数据 → mock 工作流 (is_mock=true); 项目不存在 → 404 |
| `/api/workflows/{id}/stages` | GET | org stages + events.db | 阶段运行明细 (status/agent_id=role_id/artifacts/duration_s/cost_usd); duration 从事件流推导 (stage_started→completed 时间戳差); cost 未跟踪 → null (诚实) |
| `/api/projects/{id}/timeline` | GET | events.db (org.*) | Timeline 事件聚合 (user/stage/artifact/review/error 五类); 与 SSE 同源同映射 (历史快照 vs 增量); 无事件 → [] (诚实空态); limit 截断 |
| `/api/events/stream` | GET (SSE) | events.db 轮询 | 7 类事件推送; since_seq 断点续推; 无事件库 → 单条 error (mock=true) 后关闭 (失败安全) |

审计: 端点命中 → `console.viewed` (view=project_workflow|workflow_stages|project_timeline|events_stream) — ADR-0002 读审计同语义; SSE 连接审计一次 (逐轮询会刷屏, KISS)。

## 3. RuntimeInstance 模型 (只建模型, 不实现实例)

workspace-architecture.md §4 (S10-004 调整版) 的共享契约 — 后端 `factory-console/models.py` + 前端 `models/types.ts` 双端对齐:

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 实例唯一标识 |
| project_id | string | 所属项目 |
| type | `browser` \| `terminal` | 沙箱实例类型 |
| status | `starting` \| `running` \| `stopped` \| `error` | 生命周期状态机 |
| artifact_id | string \| null | 绑定产物 (browser 预览 ux_ui/code/release 对应产物) |
| url | string \| null | browser 预览地址 (type=browser) |
| session | string \| null | terminal 会话标识 (type=terminal) |
| created_at | string \| null | UTC 时间戳 |

本 Sprint 不实现实例创建/生命周期/截图 — Browser/Terminal 与 runtime 服务由 S10-004 实现 (该服务发射 `org.runtime.*` 事件 → SSE 同映射)。

## 4. SSE 事件表 (7 类, 与前端 RUNTIME_EVENT_NAMES 同源)

| org 事件类型 | SSE 事件名 | data 契约 |
|---|---|---|
| org.workflow.stage_started | `stage.started` | {stage_id, agent_id, name} |
| org.workflow.stage_completed | `stage.completed` | {stage_id, agent_id, name, artifact_id, duration_s, cost_usd} |
| org.artifact.created | `artifact.created` | {artifact_id, type} |
| org.approval.created | `approval.required` | {stage_id, gate_id} |
| org.workflow.failed / org.artifact.failed | `error` | {stage_id, artifact_id, reason, workflow_id} |
| org.runtime.created | `runtime.created` | {instance_id, type, status, artifact_id, project_id} |
| org.runtime.status_changed | `runtime.status.changed` | {instance_id, status, previous_status} |

- **契约先行**: runtime.* 事件发射点在 S10-004 Runtime 服务 (届时依 ADR-0001 扩展路径加 EventType 枚举成员); 本 Sprint 映射/形状已由测试锁定 (SimpleNamespace 假事件, 与 SSE_EVENT_MAP / 前端 RUNTIME_EVENT_NAMES 三方对齐)。
- 其余 org.* 事件 (stage_ready/approved 等) 不进 SSE 流 (KISS, 前端订阅七类)。

## 5. 前端 runtimeClient (src/api/runtimeClient.ts)

- `runtimeClient.getWorkflow(projectId)` → `{data: WorkflowDetail, is_mock}` — 无后端 → mock 工作流 (is_mock=true)
- `runtimeClient.getTimeline(projectId, limit=200)` → `{data: TimelineEventSummary[], is_mock}` — 无后端 → mock 事件流 (is_mock=true, 打开 Workspace 可见 AI 工作事件)
- `runtimeClient.subscribeEvents(projectId, handlers)` → `{close, isMock}` — EventSource 封装:
  - 订阅全部 7 类事件 (含 runtime.*); JSON 解析失败 → {raw}
  - **断线重连**: 连接错误 → onError + 固定延迟重连 (SSE_RECONNECT_DELAY_MS=2000, 指数退避留作后续); close() 后停止
  - **isMock 检测**: 收到后端 mock error 事件 (mock:true) → isMock()=true 并停止重连 (诚实演示降级, 不无限空转)
- mock fallback 只兜底 ApiError (后端不可达/数据缺失), 其他异常照抛; mock 数据全部携带 is_mock=true (诚实标注, 不冒充真实)
- SSE 封装从 client.ts 收拢至 runtimeClient (原 openEventStream 单连接原始封装移除, 避免两套 SSE API)

## 6. 测试

**pytest 6486 全绿 (6456 基线 + 30 新, 零回归)** — tests/console/test_console_s10_runtime.py (唯一 basename `test_console_*`):

- workflow 端点: 真实 200 / mock fallback (is_mock=true, 形状对齐 workspace) / 不存在 404 / 无 org None
- stages 端点: 字段装配 / duration 从事件推导 (12.5s 确定性时间戳) / 缺 completed → None / 404
- timeline 端点: 五类聚合 + 关联维度 / 审计事件不进 Timeline / 空态 [] / limit 截断 / 404
- SSE: 五类事件名 + data 契约 / 响应头 / 无事件库 → mock error / since_seq 断点续推 (HTTP + 纯函数)
- iter_sse_events 纯函数: 未知类型跳过 / since_seq+max_polls / 轮询可见新事件 / 无 store 失败安全 / stage.completed duration
- 新增 4 测试: runtime.created / runtime.status.changed 映射 + SSE_EVENT_MAP 三方对齐 + RuntimeInstance 模型契约
- 审计: runtime 端点 → console.viewed (view=project_workflow 等) / SSE 连接 → events_stream

**vitest 187 全绿 (177 基线 + 10 新)**:

- src/test/runtimeClient.test.ts (唯一 basename): getWorkflow/getTimeline 成功 + mock fallback (is_mock 诚实) / subscribeEvents 订阅全部 7 类 (含 runtime.*) / 事件透传 / mock error → isMock 停止重连 / 断线重连 (新 EventSource) / close 后不重连 — FakeEventSource 桩 + fake timers
- api.client.test.ts: 接口清单 18 键 (新增 projectWorkflow/workflowStages/projectTimeline, 仍无 post/put/patch/delete 写面)

**tsc**: `npx tsc --noEmit` 零错。

## 7. mock fallback 确认

| 场景 | 行为 | 诚实性 |
|---|---|---|
| 项目存在但无运行数据 → workflow | 200 + mock 工作流 (is_mock=true) | 前端据 is_mock 显示演示标识, 不冒充真实 |
| 后端不可达 → getWorkflow/getTimeline | 前端 mock fallback (is_mock=true) | runtimeClient 统一 {data, is_mock} |
| 无事件库 → SSE | 单条 error 事件 (mock=true) 后关闭 | 前端 isMock() 停止重连 |
| 项目不存在 | 404 (mock 只兜底数据缺失, 不兜底不存在) | 不掩盖错误 |

## 8. 范围边界 (严格遵守)

- ✅ 只读 API + SSE; mock 全程 is_mock 标注 (mock 当证明 = 禁止)
- ✅ Core Workflow/Artifact/Approval 零修改; git diff factory-core/ factory-runtime/ desktop/ = 0
- ✅ 不写 Timeline UI (S10-003); 不实现 Browser/Terminal (S10-004); 未触碰 scripts_diag_empty.py; 未 rm
- ✅ 文件范围: factory-console/** + tests/** + docs/sprint10/implementation/S10-002-report.md; 未新增/删除测试
- ✅ 唯一 basename: runtimeClient.ts / runtimeClient.test.ts / test_console_s10_runtime.py (均仓库唯一)

## 9. 下一步 (S10-003)

- Agent Timeline UI (中间核心区): 事件流渲染 (user/stage/artifact/review/error 节点) + SSE 实时追加 + 产物按钮 + 底部持续开发输入 — 消费 runtimeClient.getTimeline + subscribeEvents ({data, is_mock} 统一入口已就绪)
- S10-004: Runtime Workspace Instance (RuntimeInstance 模型 + runtime.* SSE 契约已就绪, 实现 browser|terminal 实例 + 生命周期 + 截图)

## 10. 文件清单

| 文件 | 变更 |
|---|---|
| factory-console/api/runtime.py | 新增: 4 路由函数 + iter_sse_events + SSE_EVENT_MAP (7 类含 runtime.*) |
| factory-console/models.py | +StageRunSummary / +TimelineEventSummary / +RuntimeInstance (S10-002 部分) |
| factory-console/service.py | +get_project_workflow / get_workflow_stage_runs / get_project_timeline / build_mock_workflow |
| factory-console/web/backend/fastapi_adapter.py | +4 路由绑定 (workflow/stages/timeline/SSE StreamingResponse) |
| factory-console/web/frontend/src/api/client.ts | +projectWorkflow/workflowStages/projectTimeline + withMockFallback; SSE 收拢至 runtimeClient |
| factory-console/web/frontend/src/api/runtimeClient.ts | 新增: getWorkflow/getTimeline/subscribeEvents (断线重连 + isMock) |
| factory-console/web/frontend/src/models/types.ts | +StageRunSummary/TimelineEventSummary/RuntimeInstance + RUNTIME_EVENT_NAMES (7) + runtime.* 载荷类型 |
| factory-console/web/frontend/src/mock/runtime.ts | 新增: mockWorkflowDetail/mockStageRuns/mockTimeline (is_mock=true) |
| tests/console/test_console_s10_runtime.py | 新增: 30 测试 (端点/SSE/纯函数/审计/runtime.* 契约/RuntimeInstance 模型) |
| tests/console/test_console_s10_runtime.py 同目录 tests/console/test_console_s9_*.py | 基线不变, 零回归 |
| factory-console/web/frontend/src/test/runtimeClient.test.ts | 新增: 10 测试 (查询 mock fallback + SSE 重连/isMock) |
| factory-console/web/frontend/src/test/api.client.test.ts | 接口清单更新 (18 键) |
| docs/sprint10/implementation/S10-002-report.md | 本报告 |
