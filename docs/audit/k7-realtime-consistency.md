# K7 Realtime Consistency

> 日期: 2026-08-29

## 验证
- Backend State == API State == UI State (K7 E2E: Project 100% == Tower {COMPLETED:2} == Drill COMPLETED)
- Snapshot + restore (断线恢复, test_snapshot_consistency)
- 最终一致性 (task 变化 → tower 投影, test_realtime_consistency)
- 并发无污染 (test_concurrent_projects)

## 诚实限制
- polling-based (API 查询, 5s auto-refresh in UI)
- SSE/WebSocket Contract 已定义 (S43), 推送层未实现
