# K8 WebUI Gap Analysis

> 日期: 2026-08-29 | 纯审计

## GAP 分类
| # | GAP | 类型 | 建议 |
|---|-----|------|------|
| 1 | 旧 board 页面与新版并存 (认知负担) | P2 | HIDE 专业区 / deprecate |
| 2 | 项目列表三处 (AfProjectListView/AfProjectManage/ProjectsPage) | P2 | MERGE→Work |
| 3 | AfMonitorPage ≡ ControlTowerPage 重叠 | P2 | MOVE→Tower |
| 4 | Agent 状态双来源 (workforces vs ops) | P1 | 收敛到 ops |
| 5 | Approval 双 API (approvals vs tasks/approval) | P1 | 收敛 |
| 6 | Incident 无 UI 视图 | P3 | Tower Incidents 视图 |
| 7 | 无统一 Realtime 推送 | P3 | SSE/WS 推送层 |
| 8 | /api/board 历史遗留 | P2 | deprecate 建议 |
| 9 | 前端既有 39 测试失败 | P2 | 修复 (历史遗留) |
| 10 | Task Detail 独立页缺失 (drill 内嵌) | P3 | Work 内 Task Detail |

## 收敛原则
- 不删除功能 (HIDE 保留路由)
- 新功能全走 S43 Contract + SSOT
- 一级入口固定 3 (Conversation/Work/Tower)
