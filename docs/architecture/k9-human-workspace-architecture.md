# K9 Human Workspace — 架构设计 (Hermes CTO)

> 版本: v1.0 | 日期: 2026-08-31 | 前置: PRD (k9-human-workspace-prd.md)

## 1. 目标架构

```
User
 ↓
AfWorkspaceFrame (三栏壳, 重构)
 ├── 左栏: AfContextNav (新)     — Context 导航 (对话/工作/项目/团队/运行/审批)
 ├── 中栏: AfConversationCenter (新) — 对话 (唯一主入口, 消息卡片)
 └── 右栏: AfWorkspace (新)       — Workbench (Tab: Task/Code/Preview/Diff/Evidence)
                ↓
          所有数据 → api.client → OS (conversations/projects-os/task-trees/ops/artifacts)
```

## 2. 组件设计 (新建 3 个, 复用 2 个)

| 组件 | 类型 | 职责 | 数据源 |
|------|------|------|--------|
| `AfContextNav` | 新建 | 左栏: 对话/我的工作/项目/团队/运行/审批 (动态) | /api/conversations + /api/projects-os + /api/ops/* |
| `AfConversationCenter` | 新建 | 中栏: 会话列表 + 消息流 + 输入 + **消息卡片渲染** | /api/conversations |
| `AfWorkspace` | 新建 | 右栏: Tab 容器 (Task/Code/Preview/Diff/Evidence) + **联动接收** | /api/task-trees + /api/ops + /api/artifacts |
| `ConversationPage` (已有) | 复用改造 | 逻辑提取 → AfConversationCenter | 同上 |
| `BrowserWorkspace` (已有) | 复用改造 | Tab 骨架 → AfWorkspace | 同上 |

## 3. 三栏角色对调方案

```
现状:  AfWorkspaceFrame(AfSidebar | 路由页 main | AfConversationPanel)
目标:  AfWorkspaceFrame(AfContextNav | AfConversationCenter | AfWorkspace)
```

- **AfWorkspaceShell**: 改为渲染 AfContextNav(左) + AfConversationCenter(中) + AfWorkspace(右), 不再用路由页作 main
- **Work/Tower 页**: 保留代码与路由(钻取可访问), 但中栏主视图 = Conversation
- **AfSidebar**: 语义升级 → AfContextNav(保留项目列表区作为"项目"分组)

## 4. 联动机制 (核心: 消息 → Workspace Tab)

```
ConversationContext (App 级, 已有) 扩展:
  workspaceTab: string
  setWorkspaceTab(tab: string, payload?: object)

中栏消息发送/接收后:
  parse message.intent + message.work/artifact 关联
  → 查联动规则表 (PRD §5, 12 条)
  → setWorkspaceTab(tab) → 右栏 AfWorkspace 切换

右栏被动跟随 + 用户可手动切 (手动优先, 新消息再联动)
```

## 5. 消息卡片渲染

`AfConversationCenter` 内 `renderMessage(msg)`:
- `msg.card?.type` → 卡片组件 (需求分析/PRD/任务树/执行状态/失败诊断/审批)
- 无卡片 → 纯文本
- 卡片按钮 → 调用 api (查看→setWorkspaceTab / 批准→osDecideApproval / 修复→触发 heal)

**审批卡数据**: /api/tasks/{id}/approval (已有) → PENDING 时渲染 [批准][拒绝]

## 6. 数据流 (无第二 SSOT)

```
中栏消息 → POST /api/conversations/{id}/messages → 真实 reply (含 intent/work)
右栏 Tab 数据 → GET /api/task-trees/{id}/status | /api/projects-os/{id}/status | /api/ops/drill/{id}
审批 → POST /api/tasks/{id}/approval + /api/approvals/{id}/decide
全部经 api.client, UI 零业务状态, polling 5s (右栏)
```

## 7. 文件改动清单

**新建**:
- `components/af/AfContextNav.tsx` — 左栏
- `components/af/AfConversationCenter.tsx` — 中栏 (逻辑提取自 ConversationPage)
- `components/af/AfWorkspace.tsx` — 右栏 (Tab 容器 + 联动, 骨架取自 BrowserWorkspace)
- `components/af/AfMessageCard.tsx` — 消息卡片渲染 (6 种)

**修改**:
- `components/af/AfWorkspaceFrame.tsx` — 三栏 props 语义调整 (main→center, 加 workspace)
- `components/af/AfWorkspaceShell.tsx` — 组装新三栏
- `components/af/ConversationContext.tsx` — 加 workspaceTab 状态
- `pages/ConversationPage.tsx` — 逻辑迁移 (保留薄壳或删除)
- `api/client.ts` — 补充 Task/Evidence 查询方法 (若有缺)
- 前端测试: k6-human-console / router 断言更新 (三栏角色变化)

**不动**: 后端 OS 零改动 (全复用现有 API)

## 8. 风险与守则

- 不删 Work/Tower/ControlTower 页 (路由保留, 钻取可访问)
- 不新增 OS Core 能力 (纯前端重构)
- 右栏由联动规则驱动, 禁止"工具大杂烩"
- 所有数据来自 SSOT, UI 零业务状态
- 前端测试 + 后端回归 + tsc + build 全过才提交
