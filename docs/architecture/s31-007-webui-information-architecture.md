# S31-007 — WebUI Information Architecture (Target)

> 日期: 2026-08-31 | 依据: S31-007 Reality Audit (真实代码)

## 1. 最终一级信息架构

```
AI Factory
│
├── Home (Command Center — S31-006)
│      Goal-first 输入 + Active Work + Recent Results
│
├── Conversations (唯一主入口, 三栏中栏)
│      Natural Language → Session → Real LLM → Run
│
├── Projects
│      Project List → Project Workspace (7 子页)
│
├── Operations (收敛 /ops — 只保留真实能力)
│      Runs / Tasks / Projects / Agents (有真实 API 才保留)
│
└── Settings / Developer (收敛)
```

**原则: 用户导航"工作对象", 不是 Backend Module。**
Agent/Workflow/Artifact/Verification 不出现一级菜单。

## 2. Navigation Model

```
Primary:   Home · Conversations · Projects · Operations
Context:   左栏 (对话/项目/最近 — S31-002)
Project:   项目子页 (overview/docs/todo/workflow/runtime/quality/ops)
Workspace: 右栏动态 (S31-003)
```

## 3. Route Tree (目标, 基于真实能力)

```
/                       → Home (Command Center)
/conversations          → 会话 (中栏, 无独立路由)
/projects               → 项目列表
/projects/:id           → 项目概览 (REAL)
/projects/:id/todo      → 任务树 (PARTIAL)
/projects/:id/workflow  → 工作流 (PARTIAL)
/projects/:id/runtime   → Runtime (REAL)
/projects/:id/quality   → 质量门 (REAL)
/projects/:id/docs      → 文档 (SHELL → 标记 Planned)
/projects/:id/ops       → 运维 (SHELL → 标记 Planned)
/operations             → 运维 (收敛, 只留真实)
/settings               → 设置 (收敛)
```

## 4. Page Responsibilities

| 页面 | 职责 | Reality |
|------|------|---------|
| Home | Goal-first 入口 | REAL |
| Conversation | 自然语言 + Run 卡 + Execution Detail | REAL |
| Project Overview | 项目状态/进展 | REAL |
| Project Todo | 任务树 | PARTIAL |
| Project Runtime | 运行实例 | REAL |
| Project Quality | 质量门 | REAL |
| Project Docs | 文档预览 | SHELL |
| Project Ops | 项目运维 | SHELL |
| Operations | 全局运行 | PARTIAL |

## 5. Shell/Partial 处理

```
REAL    → 正常进入 (5 页)
PARTIAL → 保留, 标注能力范围 (2 页)
SHELL   → 不进入 Primary Nav, 标记 Planned (docs/ops)
UNUSED  → 删除入口 (17 页)
DUPLICATE → 合并 (WorkflowPage→AfWorkflowPage, ConversationPage→V2 Center)
```

## 6. P0/P1/P2

```
P0 (阻碍使用):
  P0-1 删除 17 个死页面入口 + 路由清理 (消除假象)
  P0-2 Project Docs 接真实 artifact API (SHELL→REAL)
  P0-3 Project Ops 接真实 ops API 或标记 Planned

P1 (核心闭环):
  P1-1 Task Tree 完整化 (todo → run → artifact → verification)
  P1-2 Operations 收敛 (runs/tasks/projects/agents 真实)
  P1-3 Conversation 管理 (历史/搜索)

P2 (高级):
  P2-1 Agent Monitoring
  P2-2 Expert Mode
  P2-3 文档编辑 (真实写入 API)
```

## 7. 推荐实施顺序

```
1. P0-1 死页面清理 (17 页, 低风险, 消除假象)
2. P0-2/3 Project Docs/Ops 接真实 (SHELL→REAL)
3. P1-1 Task Tree 完整闭环
4. P1-2 Operations 收敛
5. P1-3 Conversation 管理
6. P2 高级能力
```
