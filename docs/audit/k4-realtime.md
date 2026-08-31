# K4 Realtime & 一致性

> 日期: 2026-08-29

## Event → Projection
- 事件: audit_events.json (immutable/timestamped/correlation)
- 投影: 每次查询实时计算 (polling fallback)
- Realtime Contract: make_realtime_event (S43) 已定义 (REST/SSE/WebSocket 共用)

## 一致性保证
- 最终一致性: task 状态变化 → tower 投影立即反映 (test_realtime_consistency)
- 断线恢复: snapshot + restore (比较 executions/task_states/workforce; 变化→不一致检测)
- 并发: 多 project 独立投影, ID 无冲突 (test_concurrent_projects)

## 已知限制 (诚实)
- 当前 polling-based (API 查询), 未实现 SSE/WebSocket 推送
- Realtime Contract 已定义, 推送层 = 后续工作
