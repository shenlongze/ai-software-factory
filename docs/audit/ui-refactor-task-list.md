# AI Factory Human Workspace — UI 重构任务清单 (P0/P1/P2)

> 日期: 2026-08-31 | 依据: Founder 截图逐项评审 + 真实代码审计
> 原则: 一刀一刀改, 不牵出连锁修改; 每刀独立验收, 不再"改一个页面牵出十几个"

## 目标状态 (最终 IA)

```
┌────────────┬──────────────────────────┬──────────────────────┐
│  Context    │  Conversation            │  Workspace            │
│  (左)       │  (中, 第一主角)           │  (右, AI 工作现场)     │
│            │                          │                      │
│  💬 对话    │  你想完成什么？           │  Preview / Code       │
│  工作      │  [ 输入你的需求…… ]       │  Files / Task         │
│  项目      │                          │  Evidence / ...       │
│  运行      │  最近工作                 │  按当前任务动态出现    │
│  团队      │  ...                     │                      │
│  审批      │                          │                      │
└────────────┴──────────────────────────┴──────────────────────┘
```

## P0 — 信息架构 (第一刀: 首页 = Conversation Workspace)

| # | 问题 | 现状 (真实代码) | 目标 | 验收 |
|---|------|----------------|------|------|
| P0-1 | 页面主角错了: Dashboard 抢了 Conversation 的主角位 | K9 已把默认路由指向 conversation, 但中栏是"会话列表+消息流", 不是"你想完成什么"的引导 | 中栏第一屏 = 引导式对话: "你想完成什么?" + 输入框 + 最近工作 | 打开首页第一眼是对话引导 |
| P0-2 | 右边不像 Workspace, 是 Chat + 工具列表 | AfWorkspace 5 Tab 存在但面板是简单列表 | 真 Workspace: Preview/Code/Files/Task/Evidence 按任务动态出现 | 任务不同, 右栏内容不同 |
| P0-3 | 三栏比例不合理 | AfWorkspaceFrame 默认宽 (中 920/右 700) | 260 / 1fr / 520, 可拖动 | 视觉重心在中栏 |
| P0-4 | 左栏是"传统管理后台" + 内部命名泄漏 | AfContextNav 有"我的工作/项目/运行/审批", 但旧 AfSidebar 仍有 nav.workspace.conversation 泄漏 | 左栏 = 对话/工作/项目/运行/团队/审批; 彻底清除内部 key 泄漏 | 用户看不到任何 nav.workspace.* |
| P0-5 | 层级关系不清 (公司/项目/会话/工作区) | 无清晰层级语义 | 固定 Company→Work→Project→Task→Execution→Artifact; Conversation 贯穿为交互入口 | 用户随时知道自己在哪层 |

## P1 — 会话与 Workspace 体验

| # | 问题 | 现状 | 目标 | 验收 |
|---|------|------|------|------|
| P1-1 | Evidence 藏在聊天消息里 | Evidence 只是消息一部分 | Evidence = Workspace 一级对象 (独立面板) | 右栏有 Evidence Tab, 独立展示 |
| P1-2 | 工具调用暴露成普通文字 | 消息里直接显示 project_status/project_scan 等 | 折叠成"AI Factory 正在检查项目 ✓项目状态 ✓代码结构"; 点开才见 Tool 详情 | 普通用户看不到工具名 |
| P1-3 | 开发者痕迹抢注意力 | 顶栏"开发者控制台/LLM/☀" 显眼 | 开发者功能进 Settings→Developer | 首页无开发者入口抢眼 |
| P1-4 | 版本号太突出 | 左下 v1.1.360 显眼 | 弱化或进 Settings→About | 首页版本不抢眼 |
| P1-5 | 状态栏信息太多 | "hermes-default/会话11/消息24/≈3112 tokens" | 只留用户需要的; tokens 等进 Developer | 状态栏干净 |

## P2 — 数据表达与视觉统一

| # | 问题 | 现状 | 目标 | 验收 |
|---|------|------|------|------|
| P2-1 | 项目列表用任务数当主角 | "AI Factory 自身 53/156" | 项目 = 状态+最近工作+最后活动, 任务数是辅助 | 项目卡突出状态/最近工作 |
| P2-2 | 状态词汇不统一 | "开发/构想/运行/待办/审批" + "Planning/Executing/Blocked" 混用 | 统一 Work State Model (单一词表) | 全 UI 状态词一致 |
| P2-3 | AI Factory 自身项目混在普通项目里 | 与 ScorePocket/墨笺 并列 | 归入"我的工作"下 (AI Factory 作为工作项), 不扰乱层级 | 层级清晰 |

## 执行顺序 (7 步, 每步独立验收)

```
Step 1  信息架构: 首页 = Conversation Workspace (P0-1/2/3/4/5)   ← 第一刀
Step 2  Conversation: 引导式对话 + 消息卡片 + 说人话 (P1-2)
Step 3  Workspace: Evidence 一级对象 + 动态 Tab (P1-1)
Step 4  Navigation: 左栏纯净 + 层级固定 (P0-4/5)
Step 5  Project/Work: 项目卡重设计 (P2-1/3)
Step 6  Developer/Observability: 开发者痕迹收纳 (P1-3/4/5)
Step 7  视觉统一: 状态词表 + 样式 (P2-2)
```

## 第一刀 (Step 1) 详细规格

**只改中栏 AfConversationCenter 首屏 + 三栏比例 + 左栏纯净**, 不碰其他。

### 1a. 中栏首屏 = 引导式对话
```
❌ 现在: "和公司说话, 开始你的工作" (静态空态)
✅ 目标:
  ┌────────────────────────────┐
  │  💬 AI Factory              │
  │                             │
  │  你今天想做什么？            │
  │  [ 输入你想完成的事情…… ]    │
  │                             │
  │  最近工作                    │
  │  · 上次: 台球计分 (2天前)     │
  └────────────────────────────┘
```
- 空态改为引导式 (不是"和公司说话"硬话术)
- 有历史时显示"最近工作"

### 1b. 三栏比例: 260 / 1fr / 520 (可拖动)
- AfWorkspaceFrame 默认宽改小右栏, 中栏弹性

### 1c. 左栏纯净
- 清除 nav.workspace.* key 泄漏 (旧 AfSidebar 若仍在主路径则摘除)
- 左栏只留 Context 语义 (对话/工作/项目/运行/审批)

### 1d. 顶栏收敛
- "开发者控制台/LLM/☀" 弱化或收纳 (Step 6 彻底做, 第一刀先不抢眼)

## 验收 (第一刀)

- [ ] 打开 5180 首页: 第一眼是"你今天想做什么?" 引导 (非 Dashboard)
- [ ] 中栏输入真实需求 → 能对话 (LLM 理解待 Step 2, 第一刀先保持可聊)
- [ ] 左栏无任何 nav.workspace.* 泄漏
- [ ] 三栏比例 260/1fr/520 可拖动
- [ ] 全前端测试过 + tsc + build
- [ ] 不牵出其他页面修改 (只动中栏/比例/左栏/顶栏)
