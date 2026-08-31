# K8 Realtime Audit

> 日期: 2026-08-29 | 纯审计

## 当前机制
| 页面 | 机制 |
|------|------|
| ConversationPage | 无轮询 (消息流即时) |
| WorkPage | 手动刷新 (loadStatus on click) |
| ControlTowerPage | polling 5s (auto-refresh checkbox) |
| 旧页面 (Monitor) | 手动 + 旧 SSE (runtimeClient) |

## 统一性判断
- 无统一 Realtime 层: 各页面各自 polling / 手动
- OS Event (audit_events.json) → realtime_stream (K4) 存在, 但 UI 未消费
- S43 make_realtime_event Contract 已定义, 推送层未实现

## 建议 (不执行)
统一为: OS Event → Realtime Contract → WebUI Projection Update
- SSE/WebSocket 推送 (后续 Sprint)
- Control Tower 5s polling 可保留为 fallback
