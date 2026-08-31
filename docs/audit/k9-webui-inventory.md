# K9 WebUI Inventory (收敛版)

> 日期: 2026-08-29 | HEAD: (K9 commit) | v1.1.360

| 页面 | Route | 职责 | API | 数据源 | 重复 | 最终处理 |
|------|-------|------|-----|--------|------|---------|
| ConversationPage | workspace 默认 | OS Front Door | /api/conversations | OS SSOT | 否 | KEEP |
| WorkPage | workspace/work | Project/Sprint/Task/Approval | /api/projects-os + tasks/approval | OS SSOT | 否 | KEEP |
| ControlTowerPage | workspace/tower | 运营监控/钻取 | /api/ops/* | OS SSOT | 否 | KEEP |
| project/* 8 页 | project/:id | 项目 Detail | /api/projects + projects-os | OS SSOT | 否 | KEEP (项目 Detail) |
| AfCompanyHome | workspace (dashboard) | 我的公司 (旧首页) | /api/dashboard | Legacy | 与 Conversation 重叠 | HIDE (专业区) |
| AfProjectListView | workspace/projects | 项目列表 | /api/projects | Legacy | 与 WorkPage 重叠 | MERGE→Work |
| AfMonitorPage | workspace/monitor | 监控 | /api/board | Legacy | 与 Tower 重叠 | MOVE→Tower |
| AfSettings | workspace/settings | 设置 | /api/config | Legacy | - | HIDE (专业区) |
| AuditPage | workspace/audit | 审计 | /api/audit | SSOT | - | HIDE (专业区) |
| Board 系 10 页 | board | 旧控制台 | /api/board/* + /api/sessions | Legacy | 与新三页重叠 | HIDE / DEPRECATE |
