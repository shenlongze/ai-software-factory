# K7 Gap List (分类)

> 日期: 2026-08-29

## P0 (Architecture/Contract Failure)
- 无

## P1 (Production Workflow Failure)
- 无 (10 Journeys 全过 + 真实 LLM E2E)

## P2 (UX/Conversation Failure)
- Intent 规则级误判 (如"做到哪里"之前未识别 — 本 Sprint 已修 ASK_STATUS pattern)
- 需 LLM 辅助理解复杂自然语言 (DEFERRED)

## P3 (Observability)
- SSE/WebSocket 推送未实现 (polling fallback)

## P4 (Optimization)
- 通用任务 prompt 仍硬编码计算器 (software_developer)

## DEFERRED
- Task Detail 独立页 (现 drill 内嵌)
- Incident 可视化视图
- 前端既有 39 测试失败 (历史遗留)
