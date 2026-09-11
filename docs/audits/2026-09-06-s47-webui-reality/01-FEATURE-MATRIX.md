# 01 — FEATURE MATRIX (READ-ONLY)

| 功能 | 分类 | 证据 | 备注 |
|---|---|---|---|
| Home/Command Center | REAL | AfDashboard/af 入口; api.dashboard | goal-first |
| Idea 输入/新建项目 | REAL | AfSidebar/AfContextNav → api.createProject (POST /api/projects{idea}) | 真建 org project |
| Project 列表/选择/切换 | REAL | AfProjectsView ← GET /api/projects; ConversationContext projectId + URL ?project + localStorage (UI pref) | S32/S35 已修 |
| Project 概览 | REAL | AfProjectHome: detail{project/requirements/plans/tasks} ← /api/projects/{id} | 展示层 |
| Conversation (CRUD/流) | REAL | api.conversations + sendConversationMessage + messages; AfConversationCenter/Panel | SSE 见 04 |
| Session→Run | REAL | api.sessionRuns + sessionProgressCard + run-status | 关联投影 |
| Workspace 文件 | REAL | AfWorkspace 面板 ← /api/projects/{id}/workspace (root_path) | 真文件 |
| 任务 (backlog 树) | REAL | AfTodoTree ← /api/projects/{id}/tasks → toTodoTree | 真数据 |
| Workflow 详情 | PARTIAL | AfWorkflowPage/Viewer → runtimeClient.getWorkflow: 真 API 失败→mock fallback (is_mock) | 后端 workflow 在, fallback 常态? 需接 S46 run 事件 |
| 运行实例/事件 | PARTIAL | runtimeClient.listRuntimes/subscribeEvents (SSE; mock 诚实降级) | 轮询 2s + SSE |
| Approval gate 查看/批 | REAL(os 域) | AfQualityGate ← approvals API; AfWorkspace Approve → osDecideApproval | M3 org 审批 |
| Quality gate | REAL | AfQualityGate (checks 真, 禁 fake) | 旧域检查 |
| Preview iframe | REAL | AfPreviewWindow (live url/list) | 运行应用/URL |
| **ACC-* 验收 (S45)** | **BACKEND_ONLY** | acceptance_truth 后端完整 (begin/approve/request_change + GET acceptances); 前端 client 零调用 | 核心缺口 |
| **RELEASE-* (S45)** | **BACKEND_ONLY** | release_truth 后端完整 (create/gate/execute); 前端零调用 | 核心缺口 |
| Artifact 产物 | PARTIAL | AfWorkspace artifacts 区 ← /api/projects/{id}/artifacts | canonical art-* vs M3 混合? |
| Evidence/审计 | PARTIAL | AfTimeline (org.* 事件); /api/audit | 展示 |
