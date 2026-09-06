# 00 — S47-C1 Completion Report (2026-09-07)

## 1. Objective
把真实后端事件流 (/api/events/stream) 接入 WebUI Runtime 页 — 用户实时
看到当前 Project/Run/Stage 正在发生什么 (非刷新快照)。

## 2. Preflight
HEAD 07ae2908; SSE 端点真实 (events db 7928 行, S46 事件在); subscribeEvents
已封装但零 UI 订阅; data 无 seq (续推前提缺失) — 最小 additive 补上。

## 3. Files changed
backend: factory-console/api/runtime.py (1 处 additive: data 附 seq)
frontend: api/runtimeClient.ts (sinceSeq + onOpen) · hooks/
useRuntimeProjection.ts (新) · components/af/ActiveRuntimePanel.tsx (新) ·
pages/project/AfRuntimePage.tsx (+runs snapshot + panel) ·
test/af-runtime-live.test.tsx (新) · test 3 处更新 (url/runs/EventSource)

## 4. SSE integration
subscribeEvents(projectId, handlers, sinceSeq) → EventSource → onEvent →
projection; 未知事件名仅记录不崩流 (forward-compatible)。

## 5. Snapshot + Event architecture
首帧 = 真实 snapshot (projectRuns + projectWorkflow + projectTimeline 并行);
SSE = 增量 projection; 刷新 = 重新 snapshot + SSE。

## 6. reconnect / since_seq
事件 data 带 seq → lastSeqRef → subscribeEvents(sinceSeq=lastSeq) 断线重连;
后端轮询内部 since_seq 亦递增。真实 SSE E2E: since_seq=0 → 26 事件
(7865-7927); 续推 7927 → 0 (无重放, 不重不漏)。

## 7. Project isolation
useEffect [projectId] → 旧订阅 close + 新订阅 (backend project_id 过滤;
前端仅防御)。测试: switch A→B close 旧 + 订阅 B。

## 8. Runtime projection
recentEvents (seq 升序, cap 100) / currentStage (stage.started) /
lastStageCompleted / lastError (payload 兜底) / lastSeq / connection /
isMock — 纯 UI transport/projection, 无生产状态生成。

## 9. UI evidence (如可获得)
无截图环境; 组件渲染测试覆盖 (af-runtime-live 8)。

## 10. Real E2E evidence
真实 SSE (TestClient, ~/.factory): P-f43d058b S46 run 历史事件 —
REAL HISTORICAL EVIDENCE (read path); 26 事件 + 续推无重放 PASS。

## 11. Tests
af-runtime-live 8/8; runtimeClient/AfRuntimePage/AfProjectShell 更新后
36/36; 全套 553/554 (1 pre-existing todo 时间敏感)。

## 12. Regression
frontend 553/554 (attributable 0) | tsc OK | backend 237 passed 0 failed。

## 13. Truth / Governance audit
无第二 truth: 全部状态来自 backend snapshot + SSE 事件; 无 localStorage
生产事实; 无 fake event/progress; SSE contract 仅 additive (data.seq,
现有消费者兼容)。

## 14. Git commit
01d60d8b feat(webui): real-time production monitoring via SSE | NO PUSH

## 15. Push status
NO PUSH

## 16. Remaining P2
- run→calls 下钻; canonical EXS/ver/EVD drill UI; failure/repair 时间线
  细化; overview active-run 卡 (C2-C5)

## 回答
"普通用户现在能否在 WebUI 中实时看到 AI 正在做什么?" → **是**: Runtime 页
Live Production 卡 (LIVE 徽章 + Active Run + Current Stage + 最近事件流),
由真实 SSE 驱动。

"WebUI 是否仍然只是 backend truth 的 projection?" → **是**: 事件经
backend events db → SSE → 前端投影; 前端零生产状态生成。

## Verdict: S47-C1 COMPLETE
