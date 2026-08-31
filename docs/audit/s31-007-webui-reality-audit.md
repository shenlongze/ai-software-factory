# S31-007 — WebUI Reality Audit

> 日期: 2026-08-31 | 纯审计 (零修改) | 依据: 真实代码/路由/引用

---

## 1. Current UI Inventory (29 页面文件)

| 页面 | 位置 | 外部引用 | Reality |
|------|------|---------|---------|
| AfWorkspaceEntry | pages/workspace/ | 1 (App) | **REAL** — 主入口, 三栏 |
| AfProjectEntry | pages/project/ | 1 (App) | **REAL** — 项目入口 |
| AfProjectHome | pages/project/ | 2 | **REAL** — 项目概览 (fetch /api/projects) |
| AfTodoTreePage | pages/project/ | 2 | **PARTIAL** — 任务树 (3 API 真实) |
| AfWorkflowPage | pages/project/ | 1 | **PARTIAL** — 工作流 (fetch) |
| AfRuntimePage | pages/project/ | 1 | **REAL** — Runtime (projectTimeline/projectWorkflow) |
| AfQualityGatePage | pages/project/ | 1 | **REAL** — 质量门 (approvals/timeline) |
| AfProjectDocs | pages/project/ | 1 | **SHELL** — 文档 (0 API) |
| AfProjectOps | pages/project/ | 1 | **SHELL** — 运维 (0 API) |
| AfProjectManage | pages/project/ | 0 | **UNUSED** |
| AfSettings | pages/workspace/ | 0 | **UNUSED** |
| ConversationPage | pages/ | 0 | **UNUSED** — 已被 V2 Center 取代 |
| WorkPage | pages/ | 0 | **UNUSED** |
| ControlTowerPage | pages/ | 0 | **UNUSED** |
| DashboardPage | pages/ | 0 | **UNUSED** |
| ProjectsPage | pages/ | 0 | **UNUSED** |
| ProductionPage | pages/ | 0 | **UNUSED** |
| ApprovalPage | pages/ | 0 | **UNUSED** |
| ArtifactsPage | pages/ | 0 | **UNUSED** |
| AuditPage | pages/ | 0 | **UNUSED** |
| DecisionsPage | pages/ | 0 | **UNUSED** |
| IntelligencePage | pages/ | 0 | **UNUSED** |
| LifecyclePage | pages/ | 1 | **UNUSED** (仅 ReviewSections 引用) |
| ProvidersPage | pages/ | 0 | **UNUSED** |
| ReviewPage | pages/ | 0 | **UNUSED** |
| ReviewSections | pages/ | 3 | **UNUSED** (内部引用) |
| WorkflowPage | pages/ | 1 | **UNUSED** (与 AfWorkflowPage 重复) |
| AfMonitorPage | pages/ | 0 | **UNUSED** |
| AfCompanyHome | pages/ | 0 | **UNUSED** |

## 2. Reality Summary

```
REAL (5):   AfWorkspaceEntry / AfProjectEntry / AfProjectHome / AfRuntimePage / AfQualityGatePage
PARTIAL (2): AfTodoTreePage / AfWorkflowPage
SHELL (2):   AfProjectDocs / AfProjectOps
UNUSED (17): 全部零引用死页面
DUPLICATE:   WorkflowPage (≈ AfWorkflowPage) / ConversationPage (≈ V2 Center)
```

## 3. 关键发现

1. **17/29 页面是死代码** (0 外部引用) — 制造"页面很多"假象
2. **项目子页有 SHELL**: AfProjectDocs (0 API) / AfProjectOps (0 API) — 占位
3. **AfModulePlaceholder** 用于未实现页 (禁空白, 但仍是 SHELL)
4. **路由表 16 条 vs 真实渲染 2 条** (workspace conversation + project 系)
5. **项目级真实能力**: overview/todo/runtime/quality 有真实 API; docs/ops 是壳

## 4. 结论

真实产品 = 三栏 Workbench (Conversation + Workspace) + 项目工作区 (7 子页)。
其余 17 个死页面 + 2 个壳页 = 需要清理或标记。
