# K9 方向修订 — AI Factory Human Workspace (用户拍板 2026-08-31)

> 状态: 产品转向已批准。取代原"K9 WebUI Convergence"的 UI 目标(收敛方向保留, 呈现方式改为三栏 Human Workspace)。
> 这是产品级转向: 普通用户看到的不是 Dashboard, 而是「Conversation + Workbench」。

## 1. 核心理念

```
用户感知 = "我和我的公司说话" + "公司现在正在干什么"
不是: Agent Framework / 项目管理系统 / AI Workflow Engine
```

## 2. 三栏结构 (取代当前 A=项目列表/B=内容/C=聊天)

```
┌────────────┬──────────────────────────────┬──────────────────────┐
│  Context   │        Conversation          │      Workspace       │
│  我在哪?    │   我说什么? 我想做什么?       │   AI 正在做什么?       │
│  公司/项目  │   AI 怎么理解? 我批准什么?     │   文档/代码/Preview   │
│  会话/工作  │   结果是什么?                │   Browser/Terminal   │
│  团队/运行  │    (唯一主入口)              │   Diff/Task/Evidence │
└────────────┴──────────────────────────────┴──────────────────────┘
```

## 3. 左栏 Context (不是传统菜单)

- 💬 对话 / 我的工作(当前/最近/收藏)/ 项目 / 团队 / 运行中 / 审批
- 按用户身份动态: 普通用户=对话/工作/项目; 专业用户=+运行/团队/治理

## 4. 中栏 Conversation (绝对核心)

- 不是 ChatGPT 式一问一答, 是 **OS 的人机协作空间**
- 消息内嵌结构化卡片: 需求分析/PRD/任务树/审批 → [查看][继续讨论][开始执行]
- 中栏消息 → 右栏自动呈现对应工作现场

## 5. 右栏 Workspace (不是 Browser, 是 Workbench)

- 动态工具: Preview / Code / Files / Terminal / Diff / Artifact / Task / Evidence
- **由当前 Work/Conversation 决定**, 不是用户自己找工具:
  `当前 Intent → 当前 Work → 当前 Artifact → 推荐 Workspace`
- 多工具标签 (IDE/Browser 式): `Preview | Code | Files | Terminal | Task | Evidence`
- 支持分屏 (Code + Preview 同时看)

## 6. Workspace 跟着会话走 (关键)

| 用户说 | 右栏自动变 |
|--------|-----------|
| 帮我分析产品 | 📄 Product Analysis |
| 写 PRD | 📄 PRD.md |
| 创建项目开始开发 | 📊 Task Tree (Sprint/Task 状态) |
| 看现在做出来的东西 | 🌐 Preview |
| 登录功能有问题 | 🐛 Incident → Diagnosis → Repair → Diff → Test |

## 7. Work / Control Tower 不消失, 改变呈现

- Work = Project/Sprint/Task 管理 (保留, 收敛到中栏/左栏入口)
- Control Tower = 专业运营视图 (运行/等待/失败 + 钻取), 不抢占普通用户入口

## 8. 架构约束 (继承 K9 + 更严)

- Conversation = 唯一主入口
- Workspace = AI 工作现场 (数据全来自 OS Unified Contract)
- 所有数据来自 OS SSOT, UI 零业务状态
- Realtime 统一 (当前 polling, SSE 契约已定义)
- **守住**: 右栏不是"工具大杂烩", 由当前 Work/Conversation 决定

## 9. 目标关系图

```
           AI FACTORY OS
                 │
                 ▼
        ┌─────────────────┐
        │   Conversation  │  ← 唯一主入口
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        ↓                 ↓
   Conversation       Work (管理)
        │                 │
        └────────┬────────┘
                 ↓
        Dynamic Workspace (AI 工作现场)
                 │
   Code Preview Browser Files Evidence ...
```

## 10. 与现状差异 (GAP 起点)

| 维度 | 现状 | 目标 |
|------|------|------|
| 左栏 | 项目列表 (AfSidebar) | Context 导航 (公司/项目/会话/工作/团队/运行) |
| 中栏 | 内容区 (路由页) | Conversation (人机协作空间, 唯一主入口) |
| 右栏 | AfConversationPanel (聊天) | Workspace (动态工具区, 由 Work 决定) |
| 消息 | 纯文本 | 内嵌结构化卡片 + 右侧联动 |
| 页面 | 多路由页 (Work/Tower 等) | 收敛到左栏入口 + 中栏对话触发 |
