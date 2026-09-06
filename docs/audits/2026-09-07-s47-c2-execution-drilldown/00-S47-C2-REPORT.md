# 00 — S47-C2 Completion Report (2026-09-07)

## S47-C2 Status: COMPLETE

## HEAD
d9fd96d2 (feat) | S47-C1 01d60d8b → C2 d9fd96d2 | NO PUSH

## Changed files
backend: fastapi_adapter.py (+1 run-detail 端点; projectRuns+detail 合并
report 终态)
frontend: client.ts (+projectRunDetail) · domain.ts (+RunDetail types) ·
components/af/AfRunDetail.tsx (新) · ActiveRuntimePanel.tsx (run 下钻入口
+ latest-run) · pages/project/AfRuntimePage.tsx (selectedRun → detail) ·
test/af-run-detail.test.tsx (新 7)

## API added/changed
GET /api/projects/{pid}/runs/{run_id} → {run_id, status, stages, calls,
errors, totals, updated_at} (progress.json 只读薄投影; calls 仅 usage
metadata — 无 key/secret/content)
修正: progress.status 恒 "running" (写入后不改) → projectRuns + detail
合并 report.json 终态 → 真实 run status (active-run 判断正确性)。

## UI added
AfRunDetail: Run 头部 (id/status) + totals (N calls/tokens/$/s) + Stage
时间线 (✓ completed / ● running / ✗ failed / ○ pending; 中文人话 label;
repair/retest → "问题修复 (AI Repair)"/"复测 (Retest)" 徽章; 可展开:
stage 原始 id/workflow/status/note) + errors 块 + LLM Calls 表 (model/
status/tokens/latency)。
ActiveRuntimePanel: Active Run / (无 active 时) Latest Run → [Run 详情]。

## Tests
af-run-detail 7/7 (render/totals/stage 展开/repair 人话/calls 无 secret
断言 /errors/404 error/close/latest-run 入口) | C1 集 15/15 | 全套
560/561 (1 pre-existing todo) | tsc OK。

## Backend tests
2410 passed, 1 skipped, 0 failed (S45/S44/session_webui/frontend_team/
api/exec/org/release/workflow_start)。

## Real E2E (真实 S46 数据, ~/.factory — REAL HISTORICAL EVIDENCE)
GET /api/projects/P-f43d058b/runs/R1788679924187 → 200: 8 stages (含
repair 1 / retest 1 真实修复轮) + 10 calls (deepseek-v4-pro usage) +
totals (63,900 tokens / $0.0224 / 183.8s) + errors [] + status
completed (report 合并); 404 校验 PASS。

## Real data source
workflow_runs/{pid}/{run_id}/progress.json + report.json (workflow_runner
真实执行事实) → 薄端点 → WebUI 投影。无第二 truth。

## Mock audit
零新增 mock; calls usage 仅 metadata; content/key 字段不渲染 (测试断言
sk-/api_key/Bearer 不存在)。

## Project isolation
run detail 按 project_id + run_id 后端路径隔离; UI selectedRun 随
projectId 重挂 (useEffect [projectId, runId])。

## S47 attributable regression
0 (唯一失败 = pre-existing todo 时间敏感, 文件未碰)。

## Commit
d9fd96d2 feat(webui): add real-time execution drill-down control plane
NO PUSH

## Push status
NO PUSH

## 关键回答
"普通用户现在能不能从 Conversation/Runtime 看懂 AI 正在做什么?"
→ 能: Runtime 页 Live 面板 (真实 SSE) + Run 详情 (8 阶段人话 timeline,
含 AI 修复轮) + LLM calls metadata。

"用户能不能从 Run 一直下钻到 Artifact/Verification/Evidence/Acceptance/
Release?" → 部分:
- Run → Stage → Repair/Errors/Calls ✓ (C2)
- Run → ACC → RELEASE → Delivery ✓ (review 页, S47-B)
- Run/Stage → canonical art/ver/EVD 独立 drill ✗ (剩余断点: canonical
  stores 无 REST 端点; ID 经 release/ACC 可见) — 记录为 C3 backlog

## Remaining P2 (C3+)
- canonical EXS/ver/EVD 薄投影 API + 证据链 drill UI
- run detail 内嵌 artifact/verification 关联
- intervention 中心统一 (ACC/gate/block 提示进 run 上下文)
