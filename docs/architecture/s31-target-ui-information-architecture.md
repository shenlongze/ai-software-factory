# S31 — Target UI Information Architecture

> 日期: 2026-08-31 | 目标架构 (S31-002 起实施)

## 核心原则

1. **Conversation-first**: 中栏对话是唯一主入口, 用户说"我要做什么"
2. **Module 隐藏**: Agents/Workforce/Skills/Models/Workflow 全部后台, 不出现菜单
3. **左栏 = Context**: 显示"我现在在什么事上" (对话/项目/最近), 不是功能菜单
4. **右栏 = Workspace**: 当前任务所需工作空间 (动态)
5. **真实数据**: 全部来自 Production Core (S30 已验证)

## 目标 IA

```
┌──────────────────────────────────────────────────────────────┐
│ AI Factory                                    [语言] [🛠]    │
├──────────────┬───────────────────────────────┬───────────────┤
│ Context      │ Conversation (唯一入口)        │ Workspace     │
│              │                               │               │
│ ⌕ 搜索       │ "你今天想做什么?"             │ (动态, 按任务) │
│              │                               │               │
│ 对话         │ 用户: 继续开发 ScorePocket    │ ├ Preview     │
│ ● ScorePocket│ AI: 正在分析当前项目...       │ ├ Code        │
│ ○ MarkPad    │    [thinking]                 │ ├ Files       │
│              │    [tool]                     │ ├ Diff        │
│ 项目         │    [run 状态卡]               │ ├ Run         │
│ ScorePocket  │                               │ ├ Artifact    │
│  ● Active    │                               │ └ Verification│
│              │                               │               │
│ 最近         │                               │               │
│ 昨天 修排行   │                               │               │
│      PRD v3  │                               │               │
└──────────────┴───────────────────────────────┴───────────────┘
```

## 左栏 (Context) — 用户视角

```
CONTEXT
┌─────────────────────────┐
│ ⌕ Search                │
├─────────────────────────┤
│ 对话                     │
│ ● ScorePocket  (进行中)  │
│ ○ MarkPad                │
│ ○ AI Factory             │
├─────────────────────────┤
│ 项目                     │
│ ScorePocket  ● Active   │
│ MarkPad      ○ Idle     │
├─────────────────────────┤
│ 最近                     │
│ 昨天 修复排行榜          │
│     PRD v3              │
│     QA #18              │
└─────────────────────────┘
```

**删除**: Home/Agents/Workforce/Skills/Models/Policies/Audit/Settings 一级菜单。
**Settings/Policies/Audit** → 收敛到顶栏 ⚙ 或开发者模式 (用户不需每天看)。

## 中栏 (Conversation) — 不变 (已验证)

保持 V2 现状: 引导式输入 + 消息流 + 工具调用卡 + Run 状态卡 + 真实 SSE。
**不重做** — S30-004 已验证, 这是产品核心。

## 右栏 (Workspace) — 保持动态 Tab 系统

保留 V2 ALL_TABS + profile (prd/coding/debug/qa 按意图选 Tab)。
增强: 显示"当前任务"标题 (来自 Conversation 上下文), 让用户知道为何看到这些 Tab。

## 层级模型

```
用户
 ↓ 说"我要做什么"
Conversation (唯一入口)
 ↓ 自动组织
AI Factory 决定: Agent/Workflow/Tool/Skill/Model/Runtime
 ↓ 执行
Run → Task → NodeRun → Artifact → Verification
 ↓ 呈现
Workspace (动态) + Conversation (自然语言汇报)
```

**用户永远不需要看到 Module 清单。**

## 生产对象可见性

| 对象 | 用户直接看到 | 上下文出现 | Workspace 出现 | 后台隐藏 |
|------|-------------|-----------|---------------|---------|
| Conversation | ✅ | — | — | — |
| Session | ❌ | ✅ (run 卡) | — | — |
| Run | ❌ | ✅ (状态卡) | ✅ | — |
| Task | ❌ | ✅ (执行卡) | ✅ | — |
| Agent | ❌ | ✅ (名称) | ✅ | — |
| Artifact | ❌ | ✅ (链接) | ✅ | — |
| Verification | ❌ | ✅ (结果) | ✅ | — |
| Workforce/Skills/Models | ❌ | ❌ | ❌ | ✅ |
| Policies/Audit | ❌ | ❌ | ❌ | ✅ |

## Web/Desktop/Mobile 职责

```
Web:    完整三栏 (Context/Conversation/Workspace)
Desktop: 复用 Web (Tauri 壳), 可加窗口管理
Mobile:  Conversation-first 单栏 (Conversation 全屏, Context/Workspace 抽屉)
```
