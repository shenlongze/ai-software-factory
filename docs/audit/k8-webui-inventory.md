# K8 WebUI Inventory — 全量盘点

> 日期: 2026-08-29 | HEAD: 3c9f9016 (v1.1.359) | 纯审计 (HARD STOP)

## 1. 运行环境 (真实)
- WebUI: http://127.0.0.1:5180/#/workspace (200)
- Backend: http://127.0.0.1:8011 (318 API paths)
- /api/board: **返回 HTML 视图页 (非 JSON API)** — 旧 board 控制台

## 2. 页面 Inventory (29 个文件, 5554 行)
| 页面 | 路由 | Purpose | API | 状态源 | Realtime | 重复 | 保留 |
|------|------|---------|-----|--------|----------|------|------|
| ConversationPage | workspace 默认 | K6 对话 | /api/conversations | SSOT | polling | - | KEEP |
| WorkPage | workspace/work | K6 Work | /api/projects-os | SSOT | polling | 与 ProjectsPage 重叠 | KEEP |
| ControlTowerPage | workspace/tower | K6 塔 | /api/ops/* | SSOT | polling 5s | 与 AfMonitorPage 重叠 | KEEP |
| AfCompanyHome | workspace (dashboard) | 我的公司 | /api/dashboard | SSOT | - | 历史首页 | MERGE→Conversation |
| AfProjectListView | workspace/projects | 项目列表 | /api/projects | SSOT | - | 与 WorkPage 重叠 | MERGE→Work |
| AfMonitorPage | workspace/monitor | 监控 | /api/board/* | 旧 board | - | 与 ControlTower 重叠 | MOVE→Tower |
| AuditPage | workspace/audit | 审计 | /api/audit | SSOT | - | - | HIDE (专业) |
| AfSettings | workspace/settings | 设置 | /api/config/* | - | - | - | HIDE (专业) |
| AfProjectManage | workspace/manage | 项目管理 | /api/projects | - | - | 与 Work 重叠 | MERGE→Work |
| ProductionPage | workspace/production | 生产 | /api/projects | SSOT | - | 历史 | MOVE→Work Detail |
| DashboardPage | board | 旧板 | /api/board | 旧 | - | 历史 | DEPRECATE |
| DecisionsPage | board | 决策 | /api/sessions | 旧 | - | - | HIDE |
| IntelligencePage | board | 智能 | 内部 | - | - | OS 内部 | HIDE |
| LifecyclePage | board | 生命周期 | 内部 | - | - | OS 内部 | HIDE |
| ReviewPage | board | 评审 | /api/review | - | - | - | HIDE |
| ProvidersPage | board | 提供商 | /api/providers | - | - | OS 内部 | HIDE |
| WorkflowPage | board | 工作流 | /api/workflows | - | - | 历史 | HIDE |
| ArtifactsPage | board | 产物 | /api/artifacts | - | - | - | HIDE |
| ApprovalPage | board | 审批 | /api/approvals | SSOT | - | - | MOVE→Work |
| ProjectsPage | board | 项目 | /api/projects | - | - | 重复 | MERGE→Work |
| project/* 8 页 | project | 项目工作区 | /api/projects/* | SSOT | - | 项目级 | KEEP (项目 Detail) |

## 3. API 分组 (318 条)
- 新 OS API: /api/conversations(5) /api/projects-os(6) /api/ops(4) /api/task-trees(4) /api/quality(2) — **Human Console 消费**
- 历史 API: /api/board/*(10) /api/sessions(8) /api/agents(4) /api/workforces(6) /api/approvals(7) — 旧控制台消费
- Core API: /api/production-runs /api/releases /api/rollbacks /api/context /api/plugins /api/intelligence 等 — OS 能力

## 4. 结论
- 新 Human Console (Conversation/Work/Tower) 已接 SSOT, 真实可用
- 历史页面 (board 系) 与旧 API 并存, 未收敛 (认知负担)
- /api/board 是旧 HTML 控制台, 非 JSON API — 定位 = 历史遗留
