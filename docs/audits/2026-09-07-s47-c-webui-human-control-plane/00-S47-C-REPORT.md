# 00 — S47-C WebUI Human Control Plane / Real-Time Monitoring & Drill-down (2026-09-07, READ-ONLY)

> HEAD 07ae2908 (S47-B 后)。S47-C = 审计 → 判定能否进 C1。零生产代码改动。

## A. 当前 WebUI Reality
- project 子页: overview/docs/todo/workflow/runtime/quality/review/ops (8, S47-B 加 review)
- overview (AfProjectHome): 真实 run 列表 (/api/projects/{id}/runs) + counts + detail
- runtime 页 (AfRuntimePage): workflow + timeline 并行真实拉取 (快照; 无 mock)
- timeline/事件/SSE: 后端完备但**前端零组件订阅 SSE** (subscribeEvents 仅定义于 client)
- S47-B review 页: ACC/RELEASE/Delivery canonical 投影 (已接)

## B. Current User Journey (真实可达)
Project → Conversation(触发 run) → overview(runs 列表) → runtime(workflow 8 阶段 +
timeline) → workspace(文件/产物) → quality(gate) → review(验收/发布/交付) → 完成
缺口: run 运行中无实时推进感 (快照需手刷); 无 run→stage 调用的展开下钻 UI
(calls 数据在 progress 但 UI 未展示); canonical EXS/ver/EVD 无独立 drill 视图。

## C. Canonical Entity Map (SSOT → API → UI)
| Entity | SSOT | API | UI | 状态 |
|---|---|---|---|---|
| Project | org | /api/projects | overview | ✓ |
| Workflow run R* | workflow_runs/progress | /api/projects/{id}/runs · /workflow | runtime 页 | ✓ 快照 |
| Stage | progress.stages (8, 含 repair 1/retest 1) | workflow detail | AfWorkflowViewer 8 阶段 | ✓ 快照 |
| Call | progress.calls (10) | —(未单列) | 无下钻 | ⚠ GAP UI |
| Canonical run-* | nodes/runs | (无专门端点) | — | ⚠ GAP (经 ACC/RELEASE 可见 id) |
| EXS-* | exec/execution_records | —(经 release) | review 卡 id | ⚠ |
| art-* | artifacts store | /api/artifacts/{id}/content | workspace 产物 | ✓ |
| ver-* | verifications | (经 release/ACC) | review 卡 id | ⚠ 独立视图缺 |
| EVD-* | evidence files | — | — | ⚠ |
| ACC-* | acceptance | S47-B 端点 | review | ✓ |
| RELEASE-* | release_truth | S47-B 端点 | review | ✓ |
| 事件 | events db (7928 真) | /api/events/stream SSE · /timeline | runtime timeline | ✓ 快照; SSE 未接 |

## D. Real-time Architecture
- events db (SQLite) 7928 行真实事件, S46 run (P-f43d058b) org.workflow.* 全在
- /api/events/stream: SSE, project_id 过滤, since_seq 断点续推, stage.started/
  completed/artifact.created/approval.required/error — **后端完备**
- 前端: subscribeEvents (EventSource) 已封装但零 UI 订阅 → runtime 页为拉取快照
- 无轮询竞争 (拉取无写); refresh 重拉正确; project 切换按 id 重拉不串 (组件内)

## E. API Coverage
实时: SSE ✓ | runs ✓ | progress ✓ | workflow ✓ | timeline ✓
Drill: artifacts/{id}/content ✓ | ACC/RELEASE ✓ | EXS/ver/EVD 独立查询 ✗ (经
release/ACC join 可见; evidence/verification 域无 REST 读端点) — **薄 projection API 候选**

## F. Drill-down Coverage
Task(树) → Run(列表) → stage(8 阶段图) 有; run→calls 无; canonical run-*/EXS-*/ver-*/
EVD-* 无独立 drill UI (ID 出现在 review 卡; provenance 链不可点开) — P2 级缺口
(核心链 UI 终点 = ACC/RELEASE 已真接, S46 全链 ID 已展示于 review/quality)。

## G. Failure/Repair Coverage
- progress.errors (0 in S46 成功; 首轮失败 run 有 errors) + stages 含 repair/retest —
  后端记录真
- timeline error 事件类型映射有; workflow viewer 8 阶段含 repair 阶段
- UI: 失败 run 显示 status=failed + errors? runtime 页 workflow 详情含 errors 字段
  展示? 部分; 修复轮以 stage 显示 ✓ — PARTIAL (失败细节展开弱)

## H. Human Intervention Coverage
- ACC PENDING → Approve/Request Change (S47-B) ✓ | Release gate BLOCK 原因 ✓ |
  governance BLOCK → 编排自动批准 (admin) — 需人工决策点弱 (自动化了)
- Request Change → 新 repair run UI 编排未串 (P2, 已记 S47-B 报告)

## I. Mock/Fallback Audit
- runtimeClient.getWorkflow/getTimeline/listRuntimes: fetchWithMockFallback (真 API 优先,
  失败→is_mock=true 诚实) — 但 AfRuntimePage/AfWorkflowPage 直接 api.* 真端点 →
  mock 仅后端不可达兜底, 非生产常态
- backend projectWorkflow: 项目无运行数据 → mock workflow (is_mock=True 后端兜底) —
  legitimate (空态演示标注)
- S47-A "workflow detail mock fallback": 核实 = 兜底非冒充; runtime 页不落 mock
- **无 production truth violation mock**

## J. UX/IA GAP
1. 运行中 run 无实时推进 (需 SSE 订阅或轮询) — P1
2. Run→stage 展开 (当前 8 阶段静态图, calls 隐藏) — P2
3. canonical 证据 drill (EXS/ver/EVD 链可点) — P2
4. overview 无 "当前正在跑什么" 活跃卡 (runs 列表有 status, 缺醒目 active) — P1
5. failure/repair 细节展示弱 — P2

## K. P0/P1/P2
P0: 无 (无第二 truth/无 mock 冒充/SSE 后端可用)
P1: C1 实时板: overview/runtime 订阅 SSE + active run 卡 (后端全备, 纯前端接线)
P2: C2 run/calls drill; C3 EXS/ver/EVD 薄投影 API + drill; C4 failure/repair 时间线
   细化; C5 human intervention (Request Change→repair 编排)

## L. 推荐实施顺序
S47-C1 (P1, 可立即): SSE subscribeEvents 接入 runtime/overview — 实时推进 +
active 卡; 复用 events/stream (零后端改动)
S47-C2: run detail 下钻 (progress stages/calls → 面板)
S47-C3: 薄投影 API (ver/evd/EXS by run) + 证据链 drill (需最小后端 + 前端)
S47-C4: failure/repair 时间线视图
S47-C5: human intervention 状态中心 (ACC/gate/block + 动作)

## M. 可否进入 S47-C1
**YES** — C1 无 STOP: 后端 SSE/events 完备真实 (7928 事件实证); 仅前端接线;
不改 contract; 无第二 truth; 影响边界 = frontend 组件 + client 方法。

## N. STOP condition
无 STOP-1..10 触发。记录: STOP-5 未触发 (event model 充足 — SSE_EVENT_MAP +
org.* 事件已覆盖 stage/artifact/approval/error); STOP-8 不适用 (无需 LLM)。

## Verdict: S47-C audit complete — C1 可实施 (纯前端实时接线, 后端零改动)。
