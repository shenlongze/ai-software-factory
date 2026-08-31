# K5 Realtime Consistency

> 日期: 2026-08-29

## 保证
- 单一状态来源: Production/Event/Evidence → Operational State → Tower
- snapshot + restore: 断线恢复 (executions/task_states/workforce 比对)
- 最终一致性: task 变化 → tower 投影立即反映 (test_realtime_consistency)
- 并发: 多 project 独立投影无污染 (test_concurrent_projects)

## 已知限制 (诚实)
- polling-based (API 查询); SSE/WebSocket Contract 已定义 (S43 make_realtime_event), 推送层未实现
