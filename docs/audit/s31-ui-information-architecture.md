# S31-001 — WebUI Information Architecture Audit

> 日期: 2026-08-31 | 纯审计 (零修改) | 依据: V2 真实代码 + 浏览器实测

---

## 1. Current UI IA (V2 TRAE Work, HEAD dfa4a1c5)

```
┌──────────────────────────────────────────────────────────────┐
│ AI Factory  | Healthy Ready | Notifications | Help | 语言 | 🛠 │
├──────────────┬───────────────────────────────┬───────────────┤
│ Global Nav   │  Conversation (唯一主入口)      │  Workspace    │
│              │                               │               │
│ ⌂ Home       │  User/AI 消息流                │  Dynamic Tab  │
│ ▣ Projects   │  tool calls 卡                │  artifact     │
│ 智能体       │  Run 状态卡 (S30-004)         │  code         │
│   ◎ Agents   │                               │  preview      │
│   ⊞ Workforce│                               │  task         │
│   ◈ Skills   │                               │  diff         │
│   ⚡ Models   │                               │  evidence     │
│ 治理         │                               │  files        │
│   ◌ 待审批 1 │                               │  terminal     │
│   ⬡ Policies │                               │               │
│   ⎔ Audit    │                               │               │
│ 系统         │                               │               │
│   ⚙ Settings │                               │               │
│ 项目         │                               │               │
│   📁 台球计分│                               │               │
│ 我的工作     │                               │               │
│   💬 会话×8  │                               │               │
└──────────────┴───────────────────────────────┴───────────────┘
```

## 2. Current Problems

### P0 (信息架构根本问题)

| # | 问题 | 证据 |
|---|------|------|
| P0-1 | **Module 级菜单直接暴露** — 12 个菜单 (Home/Projects/Agents/Workforce/Skills/Models/Policies/Audit/Settings) 全是后台 Module | AfContextNav.tsx:53-65 |
| P0-2 | **导航点击不改变内容** — 三栏恒渲染, 导航只改高亮, 用户点"Agents/Workforce"看不到对应内容 | Shell 恒渲染三栏, activeNav 仅高亮 |
| P0-3 | **两个导航模式并存** — Global (12 菜单) + Project (8 菜单) = 20 项, 用户不知自己在哪层 | mode==='project' 分支 |
| P0-4 | **无"用户任务"视角** — 用户要的是"继续开发/修 bug/看结果", 但 UI 是"模块列表"视角 | 全是对象名, 无动词/任务 |

### P1 (体验问题)

| # | 问题 | 证据 |
|---|------|------|
| P1-1 | 英文菜单 (Home/Projects/Agents...) 与中文内容混用, 非目标用户语言 | nav items label |
| P1-2 | 会话列表混在导航最底部 ("我的工作"下 8 个 💬) | AfContextNav sessions |
| P1-3 | 项目只有一个 (台球计分演示) 但占独立区块 | projects slice(0,3) |
| P1-4 | Workspace Tab 已动态 (好), 但无"当前任务"关联标题 | ALL_TABS 有, 任务名无 |

### P2 (细节)

| # | 问题 |
|---|------|
| P2-1 | 顶栏信息过载 (Healthy/Ready/Notifications/Help/语言/主题/LLM) |
| P2-2 | 状态栏 token/模型信息暴露 (内部细节) |

## 3. 根因

**V2 把"后台 Module 清单"当成了"用户导航"** — AfContextNav 的 Global 模式直接列出所有业务模块,
这是传统管理后台思维, 不符合 Conversation-first 产品定位。

## 4. 哪些可以保留 (KEEP)

- ✅ 中栏 Conversation (唯一主入口, 真实 LLM 链) — 保留
- ✅ 右栏 Workspace 动态 Tab 系统 (ALL_TABS + profile) — 保留, 方向正确
- ✅ Run 状态卡 (S30-004) — 保留
- ✅ 会话列表 (真实数据) — 保留但重定位
- ✅ 项目列表 (真实 API) — 保留但重定位

## 5. 哪些必须重构 (REFACTOR)

- 🔄 左栏 Global 导航: 从"12 个模块菜单" → "Context (对话/项目/最近)"
- 🔄 项目模式导航: 从"8 个模块菜单" → "项目上下文 (当前任务/进展/产物)"
- 🔄 顶栏: 收敛 (开发者信息弱化)

## 6. 哪些应该删除 (REMOVE)

- ❌ Home/Agents/Workforce/Skills/Models/Policies/Audit 一级菜单 (模块不直接暴露)
- ❌ 死组件: BrowserWorkspace/AfCompanyHome/AfMonitorPage (0 引用)
- ❌ 双会话旧组件 AfConversationPanel (回退路径)
