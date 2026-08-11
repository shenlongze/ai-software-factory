# AI Factory UI/UX Architecture Design

> 版本: v1.0 (S10-013 设计稿) | 日期: 2026-08-11 | 状态: DESIGN ONLY (不写前端代码)
> 依据 (唯一): AF-PRD-v1.md / project-lifecycle.md (S10-009) / project-management-system.md (S10-010) /
> execution-engine.md + S10-011-architecture-design.md / capability-architecture.md /
> S10-012-architecture-design.md + S10-012-completion.md / ui-information-architecture.md /
> workspace-architecture.md / user-flow.md / dashboard-design.md
> 约束: 不修改后端设计 / 不新增未经确认的业务能力 / 所有设计映射已有 Domain (见 §12 映射表)

---

# 1. 产品 UI 定位

## 1.1 不是什么

```
❌ AI 代码生成器
   - 不是 IDE / 代码编辑器 / Copilot 面板
   - 不要求用户理解: 代码文件 / 分支 / 依赖 / 构建
❌ 项目管理工具 (Jira / Asana 类)
   - 不是让人填任务、开周会、盯燃尽图的"管理负担"
❌ 聊天机器人 (ChatGPT 类)
   - 不是一问一答的对话框; 是有状态、有产物的生产车间
```

## 1.2 是什么

```
✅ AI 软件公司操作系统 (AI Software Company OS)

用户打开 AI Factory 看到的是一个"软件公司"在替他工作:
  产品经理在分析需求 → 设计师在画界面 → 工程师在写代码 → 测试在验收 → 发布在打包

用户是 CEO / 产品负责人:
  做决策 (命名、审核 PRD、批准发布), 不做执行 (不写需求文档、不画图、不敲代码)
```

## 1.3 心智模型

```
用户 = CEO / 产品负责人        (决策者: 拍板、把关、给方向)
AI Agent = 员工                (产品经理/架构师/开发/测试/发布 — 各司其职)
Workflow = 公司流程            (需求分析 → 设计 → 开发 → 测试 → 发布)
Project = 产品项目             (生命周期: 想法 → 定义 → 开发 → 发布 → 维护)
```

## 1.4 用户不应理解的系统内部概念

```
以下概念属于系统内部, UI 不出现术语原文, 只出现其"人话"形态:

系统内部                 UI 呈现 (人话)
─────────────────────────────────────────────────
Scheduler                "AI 项目经理正在排期"
Dispatcher               "任务已分给开发工程师"
Capability Resolver      "找到了会做这个的员工"
Workflow Instance        "当前流程: 开发阶段"
Agent Binding            员工卡片上的"擅长领域"
Capability Registry      "员工中心"
Audit Log                "操作记录"
```

## 1.5 核心体验

```
Idea → Product → Development → Release

一句想法进来, 一个可用软件出来; 中间用户只在关键节点做决定。
```

映射: AF-PRD-v1.md §1 产品愿景 (用户像老板/产品经理: 项目为什么做、做到哪里、谁在做、下一步是什么、风险在哪里)。

---

# 2. 整体信息架构

## 2.1 两级导航

```
AI Factory
├── Workspace 层 (全局: 跨项目)
│   ├── Dashboard        工作台首页
│   ├── Projects         我的项目
│   ├── Capability Center 员工中心 (Agent/Skill/MCP/Workflow/Industry/LLM)
│   ├── Workflow Center  流程中心
│   ├── Runtime Monitor  运行监控 (全部项目 AI 活动)
│   ├── Audit            审计日志
│   └── Settings         设置
│
└── Project 层 (进入某个项目后)
    ├── Overview         项目总览
    ├── Vision           愿景
    ├── Discovery        需求探索
    ├── PRD              产品需求文档
    ├── Roadmap          路线图
    ├── Backlog          需求池
    ├── Sprint           迭代
    ├── Todo Tree ⭐     进度树 (核心)
    ├── Workflow         流程视图
    ├── Runtime          运行监控 (本项目)
    └── Logs             日志
```

## 2.2 各菜单作用 (Workspace 层)

| 菜单 | 作用 | 回答的用户问题 | Domain 映射 |
|---|---|---|---|
| Dashboard | 全局工作台: 我的项目/状态/待确认/风险 | "现在该看什么?" | PRD §7 / dashboard-design.md |
| Projects | 项目列表 + 新建 + 生命周期状态 | "我有哪些产品?" | S10-009 Project |
| Capability Center | 员工中心: Agent/Skill/MCP/Workflow/Industry/LLM | "我的公司有什么员工/能力?" | S10-012 六 Registry |
| Workflow Center | 公共流程模板库 + 实例 | "公司流程长什么样?" | S10-012 WorkflowTemplate |
| Runtime Monitor | 全局 AI 实时活动 | "AI 现在在干什么?" | S10-011 runtime |
| Audit | 全系统审计 (谁/何时/做了什么/结果) | "都发生过什么?" | S10-011 AuditStore / S10-012 capability 审计 |
| Settings | LLM 配置/主题/偏好 | "怎么配?" | workspace-architecture §6 / providers.py |

## 2.3 各菜单作用 (Project 层)

| 菜单 | 作用 | Domain 映射 |
|---|---|---|
| Overview | 项目总览: 阶段进度/健康度/下一步/风险 | S10-009 lifecycle + S10-010 Progress Intelligence |
| Vision | 产品愿景 (原始想法 + 定位) | S10-010 Vision |
| Discovery | 需求探索会话 (AI 提问 + 用户回答, 持久化) | S10-009 DiscoverySession (conversation.json) |
| PRD | 产品需求文档 (查看/审核/批准) | S10-009 product-definition.md + PRD §4.2 |
| Roadmap | 路线图: Milestone/Release Plan/关键节点 | S10-010 §五 Milestone |
| Backlog | 需求池: Epic/Feature/Story/Task 四层 | S10-010 §二 Backlog |
| Sprint | 迭代: Goal/Planning/Task 引用/Review | S10-010 §一 Sprint + PRD §4.5 |
| Todo Tree ⭐ | 进度树 (普通人视角, 最高优先级, 见 §4) | S10-010 §七 Todo Tree + Task 状态机 |
| Workflow | 流程视图: 阶段流水线 + 节点状态 (见 §5) | S10-012 WorkflowInstance + capability_snapshot |
| Runtime | 本项目 AI 实时执行监控 (见 §8) | S10-011 runtime/ + workflow-execution |
| Logs | 项目日志: 审计 + 执行记录 | S10-009 log/ + S10-011 audit.log |

## 2.4 布局骨架

```
┌─────────────────────────────────────────────────────┐
│ Header: 品牌 / 全局搜索 / LLM 状态 / 主题 / 用户        │
├──────────┬──────────────────────────┬────────────────┤
│          │                          │                │
│ Sidebar  │   Main Content           │  Context Panel │
│ (导航)    │   (页面主体)              │  (情境面板)     │
│          │                          │                │
│ Workspace│   Dashboard              │  按页面动态:    │
│ └ Project│   Todo Tree              │  任务详情       │
│    └ ... │   Workflow               │  运行信息       │
│          │   PRD / Backlog / ...    │  待审操作       │
└──────────┴──────────────────────────┴────────────────┘
```

- Sidebar: 两级导航 (Workspace → Project), 折叠模式
- Context Panel: 情境面板 — 选中任务/节点时显示详情, 不用跳页
- 移动端/窄屏: 单栏 + 抽屉 (P2, 本设计以桌面为主)

映射: ui-information-architecture.md 三栏工作台 + workspace-architecture.md 总体布局。

---

# 3. 用户完整旅程设计

## 3.1 旅程流程图

```
用户: "我要做一个台球计分 App"
  │
  ▼
┌────────────────────────────────────────────────────────────┐
│ ① 创建草稿 (DRAFT)                                          │
│    AI Factory: 创建 unnamed-project-XXX (草稿项目)           │
│    界面: 项目卡片出现 "草稿" 徽标                             │
└────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────┐
│ ② AI 需求探索 (DISCOVERY)                                   │
│    AI 产品经理 主动提问 (聊天式, 持久化):                    │
│      - 用户是谁? (目标用户画像)                               │
│      - 解决什么问题? (痛点)                                   │
│      - 核心功能? (MVP 范围)                                  │
│      - 商业方向? (收费/免费/广告)                             │
│    界面: Discovery 页 = 对话流 + 右侧"已确认信息"卡片          │
└────────────────────────────────────────────────────────────┘
  │  回答完成 → 生成 Product Definition
  ▼
┌────────────────────────────────────────────────────────────┐
│ ③ 产品定义确认 (PRODUCT_DEFINED)                            │
│    AI 提议名称: "ScorePocket 台球计分"                       │
│    用户确认命名 → 项目重命名 (ScorePocket)                   │
│    界面: 确认弹窗 [采纳建议名称] [自定义名称]                 │
└────────────────────────────────────────────────────────────┘
  │  用户确认 → CONFIRMED
  ▼
┌────────────────────────────────────────────────────────────┐
│ ④ 进入开发 (DEVELOPMENT)                                    │
│    AI 自动生成需求层级:                                      │
│      Epic → Feature → Story → Task                         │
│    生成 Sprint (目标/范围/任务引用)                          │
│    AI 排期: Scheduler 分析依赖/优先级 → 分配 Agent           │
│    Workflow 执行: 需求分析→PM→UI→架构→开发→测试→发布          │
│    界面: Todo Tree 实时刷新 + Workflow 流水线 + Runtime       │
└────────────────────────────────────────────────────────────┘
  │
  ▼
┌────────────────────────────────────────────────────────────┐
│ ⑤ 展示结果 (RELEASE)                                        │
│    产物: 可运行软件 / 测试报告 / 发布包                       │
│    界面: 发布页 + 下载 + 项目总览完成度 100%                  │
└────────────────────────────────────────────────────────────┘
```

## 3.2 用户决策点 (只做决定, 不做执行)

```
决策点 1: 产品定义命名 (采纳 AI 建议 / 自定义)
决策点 2: PRD 审核 (批准 / 修改意见 → AI 重做)
决策点 3: 设计审核 (批准 / 意见)
决策点 4: 发布审核 (批准 / 拒绝)
所有决策记录到 Decision Log (AI 可学习)
```

## 3.3 旅程中的 UI 状态示例

```
Discovery 页 (对话流):
┌──────────────────────────────────────────┐
│  AI 产品经理: 这个 App 是给谁用的?         │
│     🎯 台球爱好者   🎯 台球厅老板   ✏️ 其他 │
│  [输入你的回答...]                         │
│  ──────────────────────────────────────── │
│  已确认信息:                               │
│  ✓ 用户: 台球爱好者                         │
│  ✓ 痛点: 手动计分麻烦                       │
│  ⏳ 核心功能: (待回答)                      │
│  ⏳ 商业方向: (待回答)                      │
└──────────────────────────────────────────┘
```

映射: PRD §6 用户旅程 (Step 1-6) + S10-009 §五/§六 (DiscoverySession/rename) + S10-010 (Epic/Feature/Story/Task 生成 + Sprint) + S10-011 (Scheduler 排期 + Workflow 执行)。

---

# 4. Todo Tree 核心设计 ⭐

最高优先级页面 — 普通用户理解项目进度的唯一入口。

## 4.1 设计原则

```
1. 普通人语言: 不出现 Task ID / Sprint 编号 / Agent Binding 术语
2. 树形进度: 阶段 → 模块 → 任务, 层级不超 4 层
3. 一眼看懂: 状态色 + 完成度 % + 当前焦点
4. 可下钻: 任意节点点击 → Context Panel 详情 (不用跳页)
5. 只读投影 + 操作入口: 状态来自 Runtime/Management 数据, 页面不伪造状态
```

## 4.2 树形结构

```
ScorePocket — 整体完成度 42%
├── 产品阶段                                   (阶段节点)
│   ├── 用户分析 ✅                            (模块/任务)
│   ├── 产品定位 ✅
│   └── PRD 完成 ✅
├── 开发阶段 🔄                                (阶段节点 — 当前焦点)
│   ├── Backend 🔄
│   │   ├── 用户系统 🔄
│   │   │   ├── 数据模型 ✅
│   │   │   ├── API 开发 🔄
│   │   │   └── 测试 ⏳
│   │   └── 比赛管理 ⏳
│   │       ├── 创建比赛 ⏳
│   │       ├── 计分逻辑 ⏳
│   │       └── 排名系统 ⏳
│   └── Flutter App ⏳
│       ├── UI 设计 ⏳
│       └── 页面开发 ⏳
├── 测试阶段 ⏳
│   ├── 自动测试 ⏳
│   └── 人工验收 ⏳
└── 发布阶段 ⏳
    ├── 商店准备 ⏳
    └── 商业化配置 ⏳
```

## 4.3 节点状态语义 (全局一致)

```
✅ 完成       (Task DONE / 阶段全部子节点完成)
🔄 执行中     (Task RUNNING / ASSIGNED — 有 Agent 在做)
⏳ 待办       (Task BACKLOG/READY/AVAILABLE — 排队中)
⛔ 阻塞       (Task BLOCKED — 需人工决策/依赖未满足)
❌ 失败       (Task FAILED — 需人工干预)
👁 待审核     (Task REVIEW — 等待用户批准)
```

状态色 (与 §9 视觉规范一致): 完成=绿 / 执行中=蓝(呼吸动画) / 待办=灰 / 阻塞=紫 / 失败=红 / 待审核=橙。

## 4.4 节点展开的详情面板 (Context Panel)

点击任意任务节点 → 右侧 Context Panel 显示:

```
┌─ 任务详情 ─────────────────────────┐
│ 标题:   实现登录接口                  │
│ 状态:   🔄 执行中                    │
│ 完成人: 开发工程师 Agent             │
│ 开始:   08-11 10:30                │
│ 完成:   —                           │
│ 下一步: 联调数据库                   │
│ 阻塞:   无                           │
│ ────────────────────────────────── │
│ 历史:                               │
│  10:30 开始执行 (开发工程师)         │
│  10:31 读取需求文档                  │
│  10:35 提交代码                      │
│ ────────────────────────────────── │
│ [查看产物]  [暂停]  [手动执行]        │
└────────────────────────────────────┘
```

字段来源映射 (用户要求每 Task 展示):

| 展示字段 | 来源 |
|---|---|
| 当前状态 | Task.status (S10-010 状态机) |
| 完成人 | Task.owner / executor (S10-010 Task 模型) |
| AI Agent | instance.agent + capability_snapshot.agent.id (S10-012) |
| 开始时间 | Task.started_at / instance.start_time (S10-010/011) |
| 完成时间 | Task.completed_at / instance.end_time (S10-010/011) |
| 下一步 | Task.next_action (S10-010) + AI Project Manager 推荐 (S10-010 §九) |
| 阻塞原因 | Task BLOCKED + result/audit (S10-011) |

## 4.5 完成度计算

```
节点完成度 = 已完成子节点数 / 总子节点数 (叶子任务: DONE=100%)
阶段完成度 = 子模块加权平均 (权重 = 任务优先级, P0 权重更高)
整体完成度 = 顶层阶段完成度平均
```

## 4.6 交互

```
- 展开/折叠: 单击箭头; 全部展开/收起: 工具栏按钮
- 过滤: [全部] [执行中] [阻塞] [待审核] [失败] — 一键只看问题
- 搜索: 任务标题过滤
- 焦点定位: 点击"当前焦点" → 自动滚动到执行中节点并高亮
- 操作: 节点右键/详情面板 → [手动执行] [暂停] [重试] [批准] (走 API, 页面只发指令)
```

映射: S10-010 §七 Todo Tree + §三 Task 状态机 + S10-011 (runtime 状态) + S10-012 (capability 信息入审计)。

---

# 5. Workflow 可视化设计

## 5.1 流水线视图 (项目级)

项目 Workflow 页显示当前流程实例的流水线:

```
┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
│ 需求分析 │ → │ 产品经理 │ → │ 架构师  │ → │ 开发    │ → │ 测试    │ → │ 发布    │
│  Agent  │   │  Agent  │   │  Agent │   │  Agent │   │  Agent │   │  Agent │
└────────┘   └────────┘   └────────┘   └────────┘   └────────┘   └────────┘
   ✅            ✅           ✅           🔄           ⏳           ⏳
   完成          完成         完成         执行中        待办         待办
```

节点卡片:
```
┌─ 开发 Agent ─────────────┐
│ 状态: 🔄 执行中            │
│ 当前任务: 实现登录接口      │
│ 已耗时: 20 分钟            │
│ 产物: [代码] [测试]        │
│ 历史: 3 次执行             │
└───────────────────────────┘
```

## 5.2 节点状态

```
完成 (绿)     — WorkflowInstance SUCCESS
执行中 (蓝)   — RUNNING + 当前任务/耗时/输入/输出
等待人工 (橙) — REVIEW / 审批门 (PRD/设计/发布审核)
失败 (红)     — FAILED + 原因 + [重试]
待执行 (灰)   — 未轮到
```

## 5.3 模板 ↔ 实例 ↔ 任务 关联 (UI 呈现)

```
Workflow Center (员工中心)          Project Workflow 页
┌─────────────────────────┐        ┌────────────────────────┐
│ 模板: 软件开发流程 v1     │ 引用 →  │ 实例: ScorePocket 开发   │
│ 步骤: 需求→PM→UI→架构→   │        │ 状态: 开发阶段           │
│       开发→测试→发布      │        │ 进度: 42%               │
│ 需要角色: PM/架构/开发/测试│        │ 当前: 开发 Agent (登录)  │
└─────────────────────────┘        └────────────────────────┘
        │                                     │ 绑定
        │ 模板实例化                            ▼
        │                              Task 列表 (Todo Tree 叶子)
        ▼                              ┌────────────────────────┐
  (Capability 解析:                  │ 实现登录接口 🔄          │
   Registry → Agent/Skill 实体)     │ 实现注册接口 ⏳          │
                                    │ 权限系统 ⏳              │
                                    └────────────────────────┘
```

用户看到的关联: "我的项目跑的是'软件开发流程'模板, 现在到了开发阶段, 开发工程师在做'实现登录接口'"。

## 5.4 交互

```
- 点击节点 → Context Panel (执行详情/产物/历史)
- 审批门节点 → 高亮 [去审核] 按钮 (跳审核页)
- 失败节点 → [重试] [修改意见]
- 时间轴视图 (可选): 节点按时间展开为事件流
```

映射: S10-012 WorkflowTemplate (steps/required_agents/skills) + WorkflowInstance (capability_snapshot) + S10-011 (RUNNING→SUCCESS/FAILED + REVIEW) + PRD §4.8 (Software Development Workflow)。

---

# 6. Capability Center UI

## 6.1 定位: AI 员工中心

普通用户理解: "这是我公司的员工和他们的能力"。

```
AI 员工中心
├── 员工 (Agent)
│   ├── 产品经理 Agent    — 擅长: 用户研究 / PRD 生成 / 产品分析
│   ├── 架构师 Agent      — 擅长: 技术方案 / 系统设计
│   ├── 开发工程师 Agent  — 擅长: Java / Flutter / Code Review
│   ├── 测试工程师 Agent  — 擅长: 测试用例 / 自动化测试 / 验收
│   └── 发布 Agent        — 擅长: 打包 / 部署 / 发布检查
├── 技能 (Skill)          — Java 开发 / Flutter 开发 / 测试生成 / ...
├── 工具 (MCP)            — 数据库 / GitHub / 浏览器 / ...
├── 流程 (Workflow)       — 软件开发流程 / 数据分析流程 / ...
├── 行业 (Industry)       — 软件 / 电商 / 教育 / ...
└── 模型 (LLM Config)     — DeepSeek 默认 / 备用模型 / ...
```

## 6.2 员工卡片

```
┌─ 开发工程师 Agent ────────────────┐
│  🤖  开发工程师                   │
│      状态: ● 可用 (ACTIVE)         │
│  ──────────────────────────────── │
│  擅长:                            │
│  ✓ Java 开发                      │
│  ✓ Flutter 开发                   │
│  ✓ Code Review                    │
│  ✓ API 设计                       │
│  ──────────────────────────────── │
│  版本: v1.2  |  绑定项目: 3       │
│  成功率: 92%  |  平均耗时: 45min   │
└───────────────────────────────────┘
```

## 6.3 状态语义

```
● 可用 (ACTIVE + enabled)     — 可被调度
○ 停用 (disabled)             — 用户手动关闭
◐ 已废弃 (DEPRECATED)         — 旧版本, 历史任务仍可复现, 新任务不推荐
✖ 已归档 (ARCHIVED)           — 终态, 只读
```

## 6.4 页面结构

```
Tab 1: 员工 (Agent)     — 卡片网格 + 能力标签 + 状态筛选 + [新建员工]
Tab 2: 技能 (Skill)     — 列表 + 版本 + 状态
Tab 3: 工具 (MCP)       — 列表 + 连接状态
Tab 4: 流程 (Workflow)  — 模板卡片 (步骤预览) + [新建流程]
Tab 5: 行业 (Industry)  — 行业卡片 (关联流程)
Tab 6: 模型 (LLM)       — 提供商/模型/端点 + [测试连接] (密钥加密, 不显示明文)

通用: 搜索 + 状态筛选 ([全部][可用][停用][废弃]) + 详情侧栏
```

## 6.5 语言转换 (内部 → 人话)

| 内部 | UI |
|---|---|
| Agent | 员工 |
| Skill | 技能/擅长领域 |
| MCP | 工具 |
| WorkflowTemplate | 流程模板 |
| Industry | 行业 |
| LLMConfig | 模型配置 |
| lifecycle ACTIVE | 可用 |
| DEPRECATED | 已废弃 (仅历史任务用) |

映射: S10-012 六 Registry (agents/skills/mcps/workflows/industries/llm-configs CRUD + 生命周期 + capability_selectable) + capability-architecture.md §三 (Capability Extension 统一模型)。

---

# 7. Dashboard 设计

## 7.1 全局工作台 (Workspace Dashboard)

回答: "我的 AI 软件公司现在怎么样?"

```
┌─────────────────────────────────────────────────────────┐
│ 我的项目                          [新建项目]              │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                  │
│ │ScorePocket│ │ 记账App  │ │ 待审核    │   ← 项目卡片      │
│ │ 🟢 开发中 │ │ 🔵 定义中 │ │ 2 项待审  │                  │
│ │ 完成 42%  │ │ 完成 15%  │ │ 风险 1   │                  │
│ │ 进度条 ▓▓░│ │ 进度条 ▓░░│ │          │                  │
│ └──────────┘ └──────────┘ └──────────┘                  │
├───────────────────────────────┬─────────────────────────┤
│ 当前执行                        │ 待确认事项                │
│ 开发工程师 Agent 正在做          │ [PRD 审核: 记账App]      │
│ "实现登录接口" (ScorePocket)     │ [设计审核: ScorePocket]  │
│ 已耗时 20min  [查看]            │                         │
├───────────────────────────────┼─────────────────────────┤
│ 最近活动                        │ 风险提醒                  │
│ 10:35 开发 Agent 提交代码       │ ⚠ 记账App 里程碑 M1 延迟  │
│ 10:30 测试 Agent 通过 12 用例   │ ⚠ ScorePocket 阻塞任务 1  │
│ 10:20 PM Agent 更新 PRD        │  [查看]                  │
└───────────────────────────────┴─────────────────────────┘
```

## 7.2 区块明细

| 区块 | 内容 | Domain 映射 |
|---|---|---|
| 我的项目 | 项目卡片: 名称/状态/完成度/进度条/待审数/风险数 | S10-009 Project + lifecycle |
| 项目状态 | 生命周期阶段徽标 (草稿/探索/定义/开发/发布/维护) | S10-009 状态机 |
| 整体完成度 | 全部项目加权完成度 | S10-010 Todo Tree 聚合 |
| 当前执行 Agent | 正在执行的 Agent + 任务 + 耗时 | S10-011 runtime / S10-012 snapshot |
| 最近活动 | 事件流 (最新 N 条) | S10-011 audit / events |
| 待确认事项 | 审批门待办 (PRD/设计/发布) | S10-010 approval / user-flow §2 |
| 风险提醒 | 延迟/阻塞/失败/Agent 异常 | S10-010 §八 Progress + S10-011 Notification |

## 7.3 空态与引导

```
- 无项目: 大输入框 "描述你的想法, 比如: 我要做一个台球计分 App" + [开始]
- 有项目无执行: 显示"待你确认产品定义"引导
- 全部完成: 庆祝态 + 发布包入口
```

映射: dashboard-design.md (只读投影原则) + PRD §7 + workspace-architecture §3。

---

# 8. Runtime Monitor UI

## 8.1 定位: AI 正在做什么 (实时透明)

```
Runtime Monitor — 项目: ScorePocket
┌──────────────────────────────────────────────────────┐
│ 当前执行                                              │
│  🤖 开发工程师 Agent      [切换: 全部项目/本项目]       │
│  任务: 实现登录接口                                    │
│  状态: 🔄 执行中 (已 20 分钟)                          │
│  ─────────────────────────────────────────────────── │
│  输入:  Task 描述: 用户登录 API, JWT 鉴权...           │
│  输出:  代码提交 (feat: login api)                    │
│  工具:  ✓ 读取需求  ✓ 写代码  ✓ 运行测试               │
│  [查看产物]  [暂停]  [手动执行]                        │
├──────────────────────────────────────────────────────┤
│ 执行时间线 (实时 SSE)                                  │
│ 10:35:12  提交代码    feat: login api          ✅      │
│ 10:34:50  运行测试    12 passed 0 failed       ✅      │
│ 10:33:01  写代码      auth_service.py          🔄      │
│ 10:30:00  开始执行    开发工程师 Agent 接手     ✅      │
└──────────────────────────────────────────────────────┘
```

## 8.2 数据模型 (UI 呈现)

| 呈现 | 来源 |
|---|---|
| 当前 Agent | instance.agent + capability_snapshot.agent.id/version (S10-012) |
| 任务 | Task.title (S10-010) |
| 状态 | WorkflowInstance.status (S10-011: CREATED/RUNNING/SUCCESS/FAILED/CANCELLED) |
| 输入 | instance.input / task.description (S10-011) |
| 输出 | instance.result / artifact (S10-011) |
| 耗时 | start_time - now / end_time (S10-011) |
| 时间线事件 | runtime/agent-execution + audit.log (S10-011) |
| 能力版本 | capability_snapshot {agent/skill/mcp/llm: {id,version}} (S10-012) — 可复现"当时用的什么版本" |

## 8.3 全局监控 (Workspace Runtime Monitor)

```
全部项目 AI 活动流 (实时):
  ScorePocket   开发 Agent    实现登录接口       🔄 20min
  记账App       PM Agent      更新 PRD          ✅ 完成
  ... 
+ 筛选: 按项目 / 按 Agent / 按状态 / 按耗时
+ 每行: [查看] → 跳对应项目 Runtime
```

## 8.4 失败展示

```
  ❌ 任务失败: 实现登录接口
  原因: 依赖的前置任务 "数据库建模" 未完成
  [重试] [查看日志] [修改计划]
```

映射: S10-011 runtime/ (agent-execution/workflow-execution) + S10-012 capability_snapshot (版本可复现) + PRD §4.9 Runtime Monitoring。

---

# 9. UI 视觉规范

## 9.1 设计风格: AI Operating System

```
关键词: 智能 / 透明 / 高效 / 可信赖

参考气质: 现代 OS 系统设置 + 数据可视化面板 (非代码编辑器风格)
- 不是 IDE (无代码高亮主导)
- 不是聊天窗口 (无气泡刷屏主导)
- 是"生产车间玻璃墙" — 看得见 AI 在工作, 数据是真实的
```

## 9.2 颜色方向

```
主色板 (深色优先, 亮色可选):
  背景:   深空 #0F1115 (主) / 面板 #161A22 (次级) / 卡片 #1D232E
          亮色模式: #F7F8FA / #FFFFFF
  主色:   科技蓝 #4C8DFF (动作/链接/焦点)
  强调:   青绿 #22C55E (成功/完成)
  警示:   橙 #F59E0B (待审核/等待人工)
  危险:   红 #EF4444 (失败/错误)
  阻塞:   紫 #8B5CF6 (阻塞/依赖)
  中性:   灰 #9CA3AF (待办/禁用)

状态色语义 (全局一致, 见 §4.3):
  完成=绿 / 执行中=蓝 / 待办=灰 / 阻塞=紫 / 失败=红 / 待审核=橙
```

## 9.3 布局

```
- 三栏: Sidebar (240px, 可折叠 64px) / Main (flex) / Context Panel (320px, 可隐藏)
- 间距: 4/8/12/16/24/32 基准 (8pt 网格)
- 圆角: 卡片 12px / 按钮 8px / 输入框 8px / 标签 6px
- 字体: 系统字体栈 (中文: PingFang SC / Microsoft YaHei; 数字/等宽: SF Mono / JetBrains Mono)
- 字号: 标题 20/16 / 正文 14 / 辅助 12
```

## 9.4 组件风格

```
卡片: 深底 + 1px 边框 (#2A3140) + 阴影 (极轻) + 圆角 12px; 悬停轻微上浮
按钮: 主按钮 = 主色实底; 次按钮 = 透明 + 边框; 危险 = 红; 禁用 = 灰
标签: 状态标签 = 色点 + 文字 (● 执行中); 能力标签 = 灰底圆角
输入: 无边框玻璃感 (聚焦出现主色描边)
进度条: 细 (4px) + 圆角 + 状态色填充 + 百分比文字
图标: 线性图标 (1.5px stroke), 统一图标集
```

## 9.5 Timeline 设计

```
- 垂直时间线: 左侧时间戳 (灰) + 中部事件节点 (状态色点) + 右侧内容卡
- 节点: 8px 圆点 (状态色) + 连接线 2px (灰)
- 当前活动节点: 呼吸动画 (蓝)
- 分组: 按任务/Agent 分组折叠
- 每事件: 时间 / 执行者 / 动作 / 结果徽标 / [证据链接]
```

## 9.6 Tree 设计

```
- 缩进层级线 (浅灰 1px)
- 节点: 图标 (阶段=文件夹 / 模块=方框 / 任务=文档) + 标题 + 状态点 + 完成度%
- 当前焦点节点: 蓝色左边框高亮
- 展开/折叠: 平滑动画 (120ms)
- 虚化: 非当前阶段的已完成节点降低透明度 (减少噪音)
```

## 9.7 动效与反馈

```
- 状态变化: 颜色过渡 150ms (不闪烁)
- 执行中: 呼吸动画 (透明度 0.6→1, 1.2s 循环) — 表示"活的"
- 完成: 轻量勾选动画 (200ms)
- 错误: 红描边 + 轻微震动 (仅错误)
- 所有操作: 即时反馈 (乐观 UI) + 失败回滚提示
- 实时更新: SSE 推送, 不整页刷新
```

## 9.8 无障碍与性能

```
- 对比度: 正文 ≥ 4.5:1 (深色模式校验)
- 键盘导航: Tab 顺序合理, 树/列表方向键操作
- 状态不只用颜色表达 (色点 + 图标 + 文字)
- 首屏 < 2s; 列表虚拟滚动; 时间线懒加载分页
- 不绑定具体代码实现 (本节是视觉规范, 技术选型见 §10)
```

---

# 10. 前端技术方案建议

## 10.1 候选方案对比

| 维度 | React + TS + Vite | Vue 3 + TS + Vite | Flutter Web |
|---|---|---|---|
| 现有基础 | ✅ 已有 (workspace-architecture §8, 5180 端口) | 需新建 | 需新建 (desktop 是 Tauri) |
| 后端对接 | FastAPI REST + SSE 直接 | 同左 | 需 Dart http/SSE 封装 |
| Tree View | 成熟 (antd/TanStack/自研) | 成熟 (element-plus/自研) | 需自研 (较繁琐) |
| Workflow Graph | react-flow / xyflow 成熟 | vue-flow 可用 | 需自研画布 |
| 桌面壳 | Tauri (已有 desktop/) | Tauri | Tauri (桌面 UI 一致) |
| 团队熟悉度 | 高 (现有 console 是 React) | 中 | 低 |
| 生态 | 最大 | 大 | 中 (Web 弱于移动) |
| 首选度 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ (仅当桌面优先统一) |

## 10.2 建议: React + TS + Vite (与现有后端/桌面壳一致)

```
技术栈:
  UI: React 18 + TypeScript + Vite
  样式: CSS Modules + design tokens (CSS 变量) — 或 Tailwind (团队偏好)
  路由: React Router (两级导航: workspace / project)
  状态: TanStack Query (服务端状态) + Zustand (UI 状态)
  实时: SSE (EventSource) — 后端已有 /api/events (workspace-architecture §6)
  图表/图: xyflow (Workflow 流水线) + 自研 Tree (轻量, 可控) + 自研 Timeline
  组件: 轻量自研 + 按需 (antd 仅用基础组件, 视觉以 design tokens 覆盖)
```

## 10.3 组件映射

| UI 组件 | 建议实现 | 数据来源 |
|---|---|---|
| Tree View (Todo Tree) | 自研递归组件 (虚拟滚动, 状态点/进度条/懒加载) | GET /api/projects/{id}/todo-tree (新, 或聚合 backlog+runtime) |
| Workflow Graph | xyflow (节点=阶段/Agent, 边=顺序) | WorkflowTemplate + Instance (S10-012/011) |
| Dashboard | 卡片网格 + 区块 (自研) | 聚合 API (projects/runtime/audit) |
| Timeline | 自研垂直时间线 (SSE 增量) | GET /api/timeline?project_id= + SSE (workspace-architecture §6) |
| Chat Interface (Discovery) | 自研消息流 (气泡 + 快速选项按钮) | POST /api/projects/{id}/discovery/answer (S10-009) |
| Context Panel | 抽屉 (右侧滑入) | 任务/节点详情 API |

## 10.4 数据流

```
UI (React) → REST (FastAPI 8011) → Domain (factory-org) → 文件/Registry
UI (React) ← SSE (events) ← 执行状态实时推送
UI (React) → Context Panel ← 聚合查询 (同域)
```

## 10.5 桌面集成 (P2)

```
现有 desktop/ (Tauri 2) 壳可承载 Web UI (本地端口) — 后续将浏览器窗口包装为桌面应用
优先级低于 Web UI 本身 (先 Web 后壳)
```

映射: workspace-architecture.md §6 (API) + §8 (技术栈) + capability-architecture.md §四 (UI 独立原则 — Web UI 不是 Core, 可替换)。

---

# 11. 页面优先级

## 11.1 MVP UI (P0 — 必须最先实现)

```
P0-1: Project Dashboard (项目总览)
      - 项目卡片 + 阶段徽标 + 完成度 + 待确认 + 风险
      - 入口: 项目列表 → 详情
P0-2: Todo Tree ⭐ (进度树)
      - 阶段→模块→任务 树 + 状态色 + 完成度 + Context Panel 详情
      - 最高优先级 (用户理解项目的核心)
P0-3: Workflow Viewer (流程流水线)
      - 节点状态可视化 + 审批门高亮 + 点击详情
P0-4: Task Detail (Context Panel)
      - 任务详情: 状态/完成人/Agent/时间/下一步/阻塞/历史/产物
P0-5: Runtime Timeline (执行时间线)
      - 实时 SSE 事件流 + 当前执行 Agent + 输入/输出/耗时
```

P0 验收: 用户输入想法 → 看到 Todo Tree 树形进度 → 点任务看到详情 → 看到 AI 实时执行时间线 → 在审批门做决定。

## 11.2 P1 — 基础完整

```
P1-1: Capability Center (员工中心)
      - 六 Tab: Agent/Skill/MCP/Workflow/Industry/LLM + CRUD + 状态
P1-2: Settings (设置)
      - LLM 配置 (密钥加密) / 主题 / 偏好
P1-3: Discovery 对话流 (需求探索)
      - 聊天式问答 + 已确认信息卡片 (依赖 P0 之前的项目创建)
P1-4: PRD 查看 + 审核页 (批准/意见)
P1-5: Workspace Dashboard (全局工作台)
```

## 11.3 P2 — 高级管理

```
P2-1: Audit 全系统审计页 (筛选/搜索/导出)
P2-2: Roadmap / Milestone 视图
P2-3: Backlog 四层管理 (Epic/Feature/Story/Task 编辑)
P2-4: Sprint 管理 (计划/回顾)
P2-5: Workflow Center 模板编辑
P2-6: 全局 Runtime Monitor (跨项目)
P2-7: 桌面壳包装 (Tauri)
```

## 11.4 实施顺序建议

```
里程碑 M-UI-1 (MVP):   P0-1 → P0-2 → P0-3 → P0-4 → P0-5 (贯通主旅程)
里程碑 M-UI-2 (闭环):   P1-1 → P1-2 → P1-3 → P1-4 (员工+设置+探索+审核闭环)
里程碑 M-UI-3 (完整):   P2 全部 (管理能力)
```

每个里程碑结束: 用户实测验收 → 再进下一里程碑 (遵循 Operating Model: Build → Test → 用户验收)。

---

# 12. Domain 映射总表 (设计合规性)

所有 UI 设计均映射已有 Domain, 未新增业务能力:

| UI 设计 | 后端 Domain (已有) | 是否需要新 API |
|---|---|---|
| §2 信息架构 | PRD §7 + S10-009/010/011/012 全部 | 页面路由 (前端) |
| §3 用户旅程 | S10-009 DiscoverySession/rename + S10-010 backlog/sprint + S10-011 scheduler/workflow | 无 (复用既有) |
| §4 Todo Tree | S10-010 Todo Tree + Task 状态机 + S10-011 runtime + S10-012 snapshot | 聚合 API (todo-tree 投影, 前端/薄后端) |
| §5 Workflow 视图 | S10-012 WorkflowTemplate/Instance + S10-011 状态机 | 无 (复用 get_workflow/list_instances) |
| §6 Capability Center | S10-012 六 Registry CRUD + 生命周期 | 无 (复用 Registry 门面 get_capability) |
| §7 Dashboard | dashboard-design.md + S10-009/010/011 聚合 | 聚合 API (前端聚合 or 薄后端) |
| §8 Runtime Monitor | S10-011 runtime/audit + S10-012 capability_snapshot | 无 (复用 timeline/events SSE) |
| §9 视觉规范 | 不涉及 Domain | — |
| §10 技术方案 | workspace-architecture §8 (React 5180) | — |
| §11 页面优先级 | 上述映射 | — |

## 12.1 明确不做 (本设计范围外)

```
- 不做新后端业务能力 (不新增 Domain 模型/状态机/存储)
- 不做 Marketplace / 插件系统 UI (capability-architecture §六 为未来愿景, 未实现, 不在本设计)
- 不做多用户协作 (PRD §9 非目标)
- 不做移动端 UI (P2+ 再评估)
- 不做真实 Agent 执行逻辑 (S10-013+ 后端任务, 与本 UI 设计独立)
```

## 12.2 依赖的前置条件

```
1. S10-012 Capability Pool 已完成 (六 Registry + 门面 get_capability) ✅
2. S10-011 Execution Engine 已完成 (runtime/audit/状态机) ✅
3. S10-010 Project Management 已完成 (backlog/sprint/task/todo tree 数据) ✅
4. S10-009 Project Lifecycle 已完成 (lifecycle/discovery/rename) ✅
5. 后端聚合 API (todo-tree / dashboard 聚合) — 前端实现时新增 (薄层, 不改 Domain)
```

---

> 状态: 设计完成 (S10-013) | 下一步: 等待人工审核 → 通过后进入前端实现 (S10-014+, 另行规划)
