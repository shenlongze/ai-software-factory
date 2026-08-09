# S10-002 — Independent Acceptance Report

> 日期: 2026-08-10 | 验收人: 独立 QA (未参与实现)
> 结论: **PASS** (7 项清单全部实测通过) | 3 个问题如实记录

## 验收结果

| # | 项 | 结果 | 证据 |
|---|---|---|---|
| 1 | pytest | ✅ | 6496 passed (exit=0; 首次 1 failed 为 runtime flaky, 重跑 PASS) |
| 2 | vitest | ✅ | 187 passed (19 files) |
| 3 | tsc | ✅ | 零错 (exit=0) |
| 4 | 端点实测 | ✅ 23/23 | 独立 QA 脚本 TestClient 重装配 (非测试 helper) |
| 5 | RuntimeInstance 模型 | ✅ | 双端字段齐 + Literal 校验 (非法值被拒) |
| 6 | mock fallback | ✅ | 无运行 → is_mock=true; 不存在项目 → 404 |
| 7 | 前端 runtimeClient | ✅ | getWorkflow/getTimeline/subscribeEvents + EventSource 重连 + isMock |
| 8 | 约束核对 | ✅ | diff factory-core/runtime/desktop = 0; 无 Timeline UI/Browser; 无 rm; 无明文 key |

## 端点实测细节

```
GET /api/projects/{id}/workflow:  200 + is_mock=false + 阶段链 (字段齐);
  项目存在无运行 → 200 is_mock=true mock 链; 不存在 → 404
GET /api/workflows/{id}/stages:   200 + agent_id/duration_s (事件推导)/cost_usd;
  404 ✅
GET /api/projects/{id}/timeline:  200 + 五类聚合; 无事件 → [] 诚实空态; 404 ✅
GET /api/events/stream:           SSE event:/data: 块 + 7 业务事件映射
  (stage.started/completed, artifact.created, approval.required/completed,
   runtime.created/status.changed) + error 失败安全
```

## 发现的问题（如实记录，未修 — 交 Orchestrator）

```
1. [文档笔误] S10-002-report.md 称 pytest 6486 (6456+30), 实测 6496 — 差 10
2. [文档偏差] 报告称 client.ts "18 键", 实测 20 键 (含 3 新增)
3. [非缺陷] 任务书要求 "8 阶段链 {artifact_count}", 实际为 5 真实/6 mock 阶段链
   + artifact 对象 — 实现与 api-data-model.md §3 / UI-IA 一致,
   任务书文字未随 S10-004 设计调整 (8e8df44) 更新
```

## 结论

```
✅ PASS — S10-002 Runtime API 交付可用
(3 个问题均为文档级, 不影响功能; 问题 1-2 由 Orchestrator 修报告,
 问题 3 为设计文档文字滞后)
```
