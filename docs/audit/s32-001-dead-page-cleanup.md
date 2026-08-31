# S32-001 — WebUI Dead Page / Route Cleanup & IA Freeze

> 日期: 2026-08-31 | 状态: 完成

## 1. 删除的页面 (24 文件)

### 死页面 (20)
```
pages/根目录 (16):
  AfCompanyHome / AfMonitorPage / AfSettings / ApprovalPage / ArtifactsPage
  AuditPage / ControlTowerPage / ConversationPage / DashboardPage / DecisionsPage
  IntelligencePage / ProductionPage / ProjectsPage / ProvidersPage / ReviewPage
  WorkPage / AfProjectManage / LifecyclePage / WorkflowPage / ReviewSections

pages/workspace (4):
  AfCompanyHome / AfMonitorPage / AfProjectManage / AfSettings
```

### 死 shell 组件 (7, 整个 shell/ 目录)
```
AgentTimeline / ArtifactCenter / ExplorerNav / FactoryPanel / ProjectTree / ReviewWorkflowPanel / WorkspaceView
```

## 2. 删除原因 (验证证据)

```
- 引用扫描: 全部 0 主路径引用 (S31-007)
- 无动态 import (grep 验证)
- 无路由引用 (router.tsx 无这些页面)
- 无业务依赖 (只被测试/其他死组件引用)
- 测试依赖: 23 个测试文件测死页面 → 一并删除
```

## 3. 删除前引用扫描证据

```
AfProjectManage/ProductionPage: 0 引用 (纯死)
其余 15 页: 仅测试引用 (1-3 次) — 测试测死页面 → 删除测试
shell/ 7 组件: 0 主路径引用, 互相引用 + mock
```

## 4. 删除后的 Route Tree

```
#/workspace            → Conversation (唯一主入口)
#/workspace/conversation → Conversation (别名)
#/project/:id          → 项目概览 (REAL)
#/project/:id/docs     → 项目文档 (SHELL/Planned)
#/project/:id/todo     → 任务树 (PARTIAL)
#/project/:id/workflow → 工作流 (PARTIAL)
#/project/:id/runtime  → Runtime (REAL)
#/project/:id/quality  → 质量门 (REAL)
#/project/:id/ops      → 项目运维 (SHELL/Planned)
```

## 5. Navigation Tree (IA Freeze)

```
Primary: Home (Command Center) · Conversations · Projects · Operations · Settings
Context (左栏): 对话 / 项目 / 最近 (S31-002)
Project (子页): Overview / Docs / Todo / Workflow / Runtime / Quality / Ops
Workspace (右栏): 动态 (S31-003) — 非一级导航
```

## 6. Duplicate Resolution

```
WorkflowPage (根)      → 删除 (AfWorkflowPage 是正式实现)
ConversationPage (根)  → 删除 (V2 Conversation Center 是正式实现)
LifecyclePage          → 删除 (无产品职责, 项目有真实 lifecycle)
```

## 7-9. Remaining

```
REAL (5):   AfWorkspaceEntry / AfProjectEntry / AfProjectHome / AfRuntimePage / AfQualityGatePage
PARTIAL (2): AfTodoTreePage / AfWorkflowPage
SHELL (2):  AfProjectDocs / AfProjectOps (标记 Planned, 不伪造)
```

## 10. 下一阶段 Implementation Queue

```
S32-002 Conversation Management
S32-003 Project Management
S32-004 Project Progress
S32-005 Task Management
S32-006 Documents
S32-007 Operations
S32-008 Monitoring
```

## 验证

```
tsc: PASS
前端测试: 512/513 (af-todo-tree 历史漂移, 测试文件 69→46)
```
