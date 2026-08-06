# AI Software Factory — Vision

> 版本: v3.0 | 日期: 2026-08-06 | 状态: 与 2026-08 架构评审对齐 (20 Phase, 2159 tests)
> 关联文档: [design-principles.md](./design-principles.md) · [lifecycle-model.md](./lifecycle-model.md) · [architecture.md](./architecture.md)

## 愿景

建设 **AI 工作生命周期管理平台** —— 一个管理 AI 员工完成"真实工作"的平台: 它理解任何项目/工作在任何阶段的状态, 调度合适的 AI 能力 (不同 Agent、不同模型、不同外部工具) 持续把它推进到下一阶段, 并在每个关键决策点保留人类审核权。

软件是第一个落地的领域 (覆盖从 Idea 到 Optimization 的完整软件生命周期), 但平台的抽象 —— 任务、工作流、事件、验证、人工审核 —— 面向一切可被 AI 驱动的知识工作。

## 定位

```
AI Software Factory = AI 工作生命周期管理平台

不是 AI 开发助手 / Coding Assistant —— 不替代编码工具, 而是组织生产
不是自动生成代码的工具            —— 代码只是中间产物, 工作生命周期才是对象
不是聊天机器人 / 单个 Agent       —— 是管理 Agent 的平台
不绑定任何 AI 工具               —— 是统一抽象层, 用户不需要学习每个 AI 工具
```

对应传统软件体系:

| 传统 | AI Software Factory |
|:-----|:--------------------|
| Jira | Task Management (任务生命周期) |
| Jenkins | Workflow Engine (流程编排) |
| K8s Dashboard | Agent Management + Dashboard (可观测) |
| Confluence | Knowledge System (决策历史沉淀) |
| CI/CD | Validation System (证据链验证) |
| GitOps / CD 流水线 | Change Intelligence + Change Driven Workflow (变更驱动交付) |

## 统一抽象: 不绑定任何 AI 工具

平台对 AI 能力的抽象分五层, 用户只面对抽象, 不面对具体工具:

```
Agent (角色) ── Skills (能力)
     │
     ├── MCP Tools (外部工具: GitHub / Jira / Figma / AWS ...)
     │
     └── Runtime (执行方式: Hermes / Codex / Claude / Local)
              │
              └── LLM Provider (模型: claude / codex / gpt ...)
```

| 抽象层 | 职责 | 当前状态 |
|:-------|:-----|:---------|
| Agent | 角色与职责 (role/skills/status) | ✅ AgentRegistry (Phase 4B) |
| Skill | 能力声明 (SKILL.md + meta.json) | ✅ SkillRegistry |
| MCP | 外部工具接入 (GitHub / Jira / Figma / AWS) | 🚧 mcp/ 目录已预留, 规划中 |
| Runtime | 执行方式 (echo/hermes 适配器实跑) | ✅ RuntimeAdapter, Catalog/Registry/Adapter 三层分离 |
| LLM Provider | 模型抽象 (claude / codex / gpt ...) | 🚧 未抽象, Phase 8 核心 |

**per-role 执行偏好**: `runtime_preferences` 字段 (Phase 6A 已建) 承载每个角色的执行偏好 —— 同一个平台上, 架构师用 Claude 思考、开发者用 Codex 写码、测试员用 Hermes 跑验证:

```yaml
runtime_preferences:
  architect:  { provider: claude }
  developer:  { provider: codex }
  tester:     { provider: hermes }
```

用户声明"要什么能力" (角色/技能/偏好), 平台负责"找谁执行"。换工具 = 改配置, 不是改流程。

## 核心理念: 任意阶段接入

Factory 不是"从零开始建项目的脚手架"。**一个项目可以带着它已有的任何状态进入 Factory**: 只有一个 Idea、已经写完的 PRD、画好的设计稿、正在开发的代码库、还是已经在生产运行的系统。Factory 的核心能力是:

> **理解项目当前处于生命周期的哪个阶段, 补齐该阶段缺失的上下文, 然后继续推进。**

接入不是"导入"而是"挂载": 通过 `workspace`/`project` 层挂载项目 (workspace.yaml + projects/*/project.yaml, 引用真实仓库), 通过 `task` 层把当前要推进的工作表达为任务, 通过 `workflow` 层选择从当前节点开始的推进路径。已有的代码、文档、git 历史都是证据与上下文, 不需要重建。

| 接入点 | Factory 能理解什么 | 如何继续推进 |
|:-------|:-------------------|:-------------|
| Idea | 项目描述、tech_stack、仓库 (可为空) | `task create` 定义探索/调研任务 → workflow |
| PRD / 设计稿 | 仓库中的文档即上下文, 任务描述即需求 | task → 任务拆解 → assignment |
| 开发中的代码 | git 状态、提交历史、变更路径 (Phase 6C/6D) | `git diff` → `change analyze` → L4 验证 |
| 存量代码 | project.yaml 技术栈映射 + Skill 装配 | 按角色/技能分派任务 |
| 生产系统 | 事件流、指标、变更记录 | Monitoring → Optimization 回路 (Phase 5B/6D/6E) |

## 能力闭环

Factory 已实现一条完整的、端到端可运行的生产闭环:

```
Workspace → Project → Task → Workflow → Agent → Assignment → Execution
    → Runtime (Hermes 等) → Validation (L1-L4) → Recovery → Dashboard
    → Metrics → Git → Change Intelligence → Change Driven Workflow
```

- **Workspace / Project** (Phase 6A): 多项目组织, 每项目独立仓库与定义 (含 runtime_preferences)。
- **Task / Workflow** (Phase 3-4): 任务状态机 + 声明式流程引擎 (feature-delivery / bug-fix / release 等内置定义)。
- **Agent / Assignment / Execution** (Phase 4B): 注册表、分配器、执行派发, 全链路事件审计。
- **Runtime Adapter** (Phase 4B1/4C1/5A1): 执行出口唯一, Hermes 适配器实跑, Catalog/Registry/Adapter 三层分离。
- **Validation** (Phase 3A/6D): L1 Factory / L2 Workflow / L3 Artifact / L4 Change, 独立于 Agent 的证据链验证。
- **Recovery** (Phase 4C3): checkpoint + 事件回放, 断点续跑不依赖对话记忆。
- **Dashboard / Metrics** (Phase 4C4/5B/6B): 16 个视图 + 项目维度指标聚合。
- **Git / Change Intelligence / Change Driven Workflow** (Phase 6C/6D/6E): git 只读接入 (可选能力)、提交任务关联、L4 判定、触发器驱动 "提交即发布" 链式交付。

## 核心价值

| # | 价值 | 含义 | 工程锚点 |
|:--|:-----|:-----|:---------|
| 1 | 管理项目上下文 | 每个项目的定义、状态、历史有唯一事实源, 多项目不串扰 | Event 唯一事实源 + Workspace Layer (Phase 6A) |
| 2 | 理解项目当前状态 | 任何时刻知道项目/任务处于生命周期的哪个节点、卡在哪 | Change Intelligence + L4 Validation (Phase 6C/6D) |
| 3 | 调度不同 AI 能力 | 按角色偏好把工作派给合适的 Agent / 模型 / 工具 | Runtime + Orchestration + runtime_preferences |
| 4 | 管理任务生命周期 | 任务从创建到交付的完整状态机, 全程可追踪可恢复 | Task→Workflow→Assignment→Execution→Validation→Recovery |
| 5 | 保存过程和决策历史 | 过程与决策可审计, 知识沉淀为企业资产 | Event + ADR + Checkpoint |
| 6 | 人工审核节点 | 产品决策的最终裁决权在人, 平台提供审核台 | 三挡板 + Decision Gate + validate 退出码 |
| 7 | 任意阶段接入 | 项目带任何已有状态进入, 从当前节点继续而非重建 | 12 阶段生命周期 + 4 类接入点 (Idea/已有代码/开发中/生产) |

> 7 项价值在工程上落实为可落地特性: **可管理 / 可观察 / 可验证 / 可恢复 / 可替换 / 可积累 / 可复制** (见 design-principles.md)。

## 用户

- **工程师** — CLI 主入口: 创建任务、跑流程、看状态、恢复断点
- **技术负责人** — Dashboard 观察工厂运行、Agent 健康、质量指标、变更流
- **管理层** — 项目进度、风险、交付质量总览 (Projects View + Metrics)
- **人类审核员** — (Web UI 规划) 审核台: 确认 PRD/UI、审核 AI 输出、批准产品决策

## 成功标准

- 一个任务从创建到交付全程可观察、可恢复、可验证
- 项目可带任意已有状态接入, 从当前节点继续推进而非重建
- 多项目并行生产, 知识跨项目复用
- 新 Runtime / 新 Provider / 新角色 / 新 Skill / 新 MCP / 新工作流声明式接入 (零核心代码改动)
- 自动化指标达标: first_attempt_success > 95%、path_errors = 0、human_intervention 最小化
- 变更可驱动交付: git 提交 → L4 验证 → 触发器 → 目标工作流 (提交即发布)
- 换掉任何 AI 工具 (Hermes / Codex / Claude) 不影响平台运转
