# AI Factory 产品 PRD v1.0

> 状态: 冻结待确认 | 日期: 2026-08-11 | 范围: 产品定义 (Workspace / Project Lifecycle /
> Execution OS / Agent Workflow) — **UI Design 之前必须先冻结本 PRD**
> 关联: docs/design/project-lifecycle.md / project-management-system.md / execution-engine.md

---

## 1. 产品愿景

AI Factory 不是一个代码生成器，而是一个**由 AI 员工组成的软件公司操作系统**。

用户像老板/产品经理一样：
> 项目为什么做、做到哪里、谁在做、下一步是什么、风险在哪里。

核心差异：
- 传统软件: 项目管理工具辅助**人**管理项目
- AI Factory: **AI 项目经理**主动管理 **AI 团队**完成项目

---

## 2. 目标用户

- 非程序员 (有想法, 要软件): 输入一句需求 → 获得可用软件
- 独立开发者/创业者: 监督 AI 团队生产, 在关键节点决策
- 公司/团队: 多项目并行, 能力资产沉淀

---

## 3. 顶层结构

```
AI Factory
│
├── Workspace                 # 用户工作空间 (项目容器)
│   ├── Project A             # 软件项目 (生命周期主体)
│   ├── Project B
│   └── Workspace Config
│
└── Factory Capability Pool   # 公共能力池 (Factory Registry — 不属于 Project)
    ├── Organizations / Industries / Agents / Skills
    ├── MCPs / Workflows / LLM Providers / Templates
```

**关键约束:**
- Agent/Skill/MCP/Workflow/Industry/LLM 属 Factory Registry (公共资源), 不属于 Project
- Project 只持有 **Workflow Instance** (公共 Workflow 的实例化 + 运行参数)
- 所有 Agent/Skill/MCP/Workflow 执行绑定 `project_id`; 运行数据写入对应 project runtime

---

## 4. Project Execution System

### 4.1 Project Lifecycle

```
DRAFT → DISCOVERY → PRODUCT_DEFINED → DESIGN → ARCHITECTURE
  → CONFIRMED → DEVELOPMENT → RELEASE → MAINTAIN
兼容保留: ACTIVE / MAINTAINED / ARCHIVED (旧数据宽容解析)

转换表 (受控, 单向, archived 终态):
  draft→(discovery,archived) | discovery→(product_defined,archived)
  product_defined→(design,archived) | design→(architecture,archived)
  architecture→(confirmed,archived) | confirmed→(development,archived)
  development→(release,archived) | release→(maintain,archived)
  maintain→(archived,) | active→(maintained,archived) | maintained→(archived,)
```

### 4.2 Product Definition

```
输入: 用户想法 → Product Discovery Session (AI 产品经理沟通)
确认项: 产品方向 / 用户痛点 / 用户画像 / 使用场景 / 核心功能 / MVP 范围 /
        使用方式 (Web/Mobile/Desktop/API) / 商业方向
输出: product-definition.md (产品名称建议/定位/核心价值/用户群体/功能列表/产品边界)
沟通过程持久化: discovery/conversation.json (questions/answers, 可追溯)
```

### 4.3 Requirement Management

```
Backlog 层级 (需求树 — 与 Sprint 无关):
  Epic (月/季度) → Feature (周/月) → Story (周) → Task (小时/天)

Task 完整状态:
  { id, title, description, priority, criticality, status, owner, executor,
    created_time, start_time, end_time, dependency, predecessor, next_action,
    workflow, agent, skill, result, evidence }

Task 生命周期: Created → Backlog → Sprint Planning → Sprint Active
  → Running → Review → Done
  异常: BLOCKED / FAILED / CANCELLED
```

### 4.4 Agile Management

```
Roadmap → Milestone (生死节点) → Release Plan → Key Node
Project Management: backlog / sprint / risk / metrics / decisions
Sprint 是执行窗口 (引用 Task, 不包含): Sprint-001 → Task-A ref / Task-C ref
一个 Task 可延期/转移 Sprint/重新规划 — 需求不变
```

### 4.5 Sprint Management

```
Sprint: { goal, planning, task_references, daily_progress, review }
AI Sprint Planning: 用户输入目标 (如 "两周完成 MVP") → AI 分析可用 Agent/
任务/优先级 → 推荐 Sprint 计划 → 用户确认或调整
```

### 4.6 Task Management

```
任务必须完整可审计 (谁什么时候干了什么):
  Task.history: [ {time, actor, action, result} ]
回答: 昨天 AI 干了什么? 为什么延期? 谁阻塞? 当前进度?

绑定: 所有 Agent 执行任务必须绑定 project_id + sprint_id + task_id
```

### 4.7 AI Task Scheduler

```
Task Scheduler Agent 负责:
  Backlog → 分析 (优先级/依赖/资源/风险) → 生成执行计划
  → 创建 Workflow Instance → 分配 Agent

自动执行规则 (默认):
  同一 Project Max Parallel Task = 5 (Project/Workspace/Global 可覆盖)
  并行条件: dependency == none AND resource conflict == false
            AND concurrency < limit
  否则串行 (依赖链: Task A → Task B)
```

### 4.8 Workflow Execution

```
Workflow Instance: Input → Agent Chain → Tool Execution → Output → Review → Next Step

Software Development Workflow (公共资源默认):
  Requirement Analysis → PM Agent → UI Agent → Architect Agent
    → Developer Agent → Test Agent → Release Agent

Project binding:
  workflow_instance: {workflow_ref: software-development-v1, parameters: {industry}}
  agents: [PM-Agent-v2, Architect-Agent-v3, Flutter-Agent, ...]
  skills: [flutter-development, test-generation]
  mcps / industry

Execution Mode: Auto (默认) / Manual (▶ Execute + Pre-check Agent 条件检查)
```

### 4.9 Runtime Monitoring

```
runtime/ (AI Runtime Data — 不进产品/知识索引):
  agent-execution / skill-execution / mcp-calls / llm-calls
  workflow-instances / state / context

Project Timeline (透明化 — 什么时候/谁/干了什么/进度/下一步):
  普通用户视角: 项目进度条 + 当前阶段 + 正在执行 Agent + 下一步 + 风险
```

### 4.10 Audit Log

```
log/ (Audit Data):
  user-action / agent-action / decision-history / audit-trail
管理状态存 management/; 执行过程存 runtime/; 禁止交叉污染
```

---

## 5. Agent Workflow (六角色 + 调度)

```
AI 团队 (Factory Registry):
  Product Manager Agent (需求分析/产品定义)
  UI/UX Designer Agent (设计)
  Architect Agent (技术方案)
  Developer Agent (编码)
  QA/Tester Agent (测试)
  Release Agent (发布)

执行: AI Project Manager 调度 → Task Scheduler → Agent Dispatcher → 并行执行
用户监督: 关键节点审核 (PRD/设计/发布门) + 优先级 Override + 手动执行
```

---

## 6. 用户旅程

```
Step 1: 输入想法 "我要做一个 AI 台球训练助手"
        → 创建 unnamed-project-001 (DRAFT)
Step 2: AI Product Manager 启动 Product Discovery (画像/痛点/竞品/核心价值/MVP/功能/商业模式)
        → product-definition.md
Step 3: 生成 PRD + UI Design System + Prototype
Step 4: 用户确认名称 "ScorePocket" → rename (事务) → CONFIRMED
Step 5: 创建开发团队 → 自动加载 Software Industry Workflow + 六 Agent
Step 6: 进入 Sprint-001 (Goal: 登录+计分核心) → Task 自动拆解/调度/执行
        → Todo Tree 实时可见 → 风险/下一步 AI 主动提醒
```

---

## 7. 左侧菜单 (Workspace + Project)

```
Workspace: Projects / Organizations / Industries / Skills / Agents / MCP /
           Workflows / LLM Config / Settings
Project:   Overview / Product (Vision/Discovery/PRD/Design) /
           Roadmap (Milestone/Release Plan) / Backlog (Epic/Feature/Story/Task) /
           Sprint / Todo Tree ⭐ / Workflow / Runtime / Logs / Knowledge / Settings
```

---

## 8. 验收标准 (v1.0 冻结基线)

```
场景1: 输入 "我想做一个台球计分App" → 创建 Draft (DRAFT, unnamed)
       → Product Discovery Session → AI 提问 (持久化)
场景2: 确认名称 ScorePocket → rename 事务 → CONFIRMED (目录/索引/引用全更新)
场景3: 既有项目 (MarkPad/AI Factory/TimeOn) 不受影响
场景4: Agent 执行绑定 project_id, runtime 数据隔离
场景5: Sprint 创建 (引用 Task) → Task Scheduler 自动调度 → Todo Tree 可见
场景6: 用户 Override 优先级 → Decision Log 记录 → AI 可学习
```

---

## 9. 非目标 (v1.0 不做)

```
- 不做 Workspace 级 Idea Pool (Idea 属于 Project)
- 不做 RAG / Mobile / Enterprise Connector
- 不做多用户协作 (单用户 + AI 团队)
- UI 设计在本 PRD 冻结后启动 (不先画页面)
```

---

## 10. 冻结声明

```
本 PRD v1.0 为 AI Factory 产品基线。
后续实现 (S10-009+): Project Lifecycle → Project Management → Execution Engine
任何实现不得偏离本 PRD; 变更走 Decision Log + 用户确认。
```
