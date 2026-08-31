# S31-007 — Page Contract & Capability Matrix

> 日期: 2026-08-31 | 依据: 真实代码

## 1. Capability Matrix (全量)

| Area | Page | Capability | API | Production Object | Reality |
|------|------|-----------|-----|-------------------|---------|
| Home | Command Center | Goal 输入 | sessions | Session | REAL |
| Home | Active Work | 运行概览 | /api/ops/overview | Project/Run | REAL |
| Conversation | Main | Natural Language | POST /api/sessions/{id}/messages?stream=1 | Session/Run | REAL |
| Conversation | Streaming | SSE | stream=1 | Run/Event | REAL |
| Conversation | Run 卡 | Session→Run | GET /api/sessions/{id}/runs | Run | REAL |
| Conversation | Execution Detail | Stages 展开 | /api/sessions/{id}/runs | Run/Stage | REAL |
| Project | List | 项目列表 | /api/projects-os | Project | REAL |
| Project | Overview | 项目状态 | /api/projects/{id} | Project | REAL |
| Project | Todo | 任务树 | create/updateBacklogFeature | Task | PARTIAL |
| Project | Workflow | 工作流 | fetch (projectWorkflow?) | Workflow | PARTIAL |
| Project | Runtime | 运行实例 | /api/projects/{id}/runtimes | Runtime | REAL |
| Project | Quality | 质量门 | approvals/timeline | Verification | REAL |
| Project | Docs | 文档预览 | — (0 API) | Artifact | SHELL |
| Project | Ops | 项目运维 | — (0 API) | — | SHELL |
| Workspace | Task | 任务面板 | /api/projects-os/{id}/status | Task | REAL |
| Workspace | Code | 代码 | /api/artifacts/{id}/content | Artifact | REAL |
| Workspace | Preview | 预览 | artifact content | Artifact | REAL |
| Workspace | Diff | 差异 | artifacts (diff) | Artifact | REAL |
| Workspace | Evidence | 验证 | /api/ops/drill | Verification | REAL |
| Workspace | Files | 文件 | /api/artifacts | Artifact | REAL |

## 2. Page Contract 模板 (代表页)

### Conversation (REAL)

```
Purpose:   用户通过自然语言驱动 AI Factory
User:      所有用户
Entry:     Home 输入 / 左栏会话
Data:      sessions + messages + runs
API:       POST /api/sessions/{id}/messages?stream=1, GET /{id}/runs
Objects:   Session / Run / Stage
Actions:   发送 / 展开 Run Detail
Loading:   消息加载态
Empty:    Welcome Hero (Command Center)
Error:    静默降级 (不伪造)
Real-time: SSE 流式
Nav:       Home / Projects
```

### Project Docs (SHELL → Planned)

```
Purpose:   查看项目文档
User:      项目成员
Entry:     项目子页 docs
Data:      (无 — 未接 API)
API:       — (需接 /api/artifacts)
Objects:   Artifact
Actions:   预览 (未来)
Loading:   —
Empty:     占位 (AfModulePlaceholder)
Error:     —
Real-time: 无
Nav:       Project 子页
```

## 3. 空壳处理决策

```
SHELL 页面 (docs/ops):
  → 不进入 Primary Navigation
  → 标记 "Planned"
  → P0-2/P0-3 接真实 API 后转 REAL

UNUSED 页面 (17):
  → 删除路由入口
  → 保留文件 (未来参考) 或归档

DUPLICATE:
  → WorkflowPage → 并入 AfWorkflowPage
  → ConversationPage → 删除 (V2 Center 取代)
```

## 4. 实施顺序 (对应 P0/P1/P2)

```
P0-1: 删除 17 死页面入口 + 路由收敛
P0-2: Project Docs → 接 /api/artifacts (REAL)
P0-3: Project Ops → 接真实 ops 或标记 Planned
P1-1: Task Tree 完整闭环 (todo→run→artifact→verification)
P1-2: Operations 收敛
P1-3: Conversation 历史/搜索
P2:   Agent Monitoring / Expert Mode / 文档编辑
```
