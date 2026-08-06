# AI Software Factory — Vision

> 版本: v2.0 | 日期: 2026-08-06 | 状态: 与 Phase 6E 实现对齐
> 关联文档: [design-principles.md](./design-principles.md) · [lifecycle-model.md](./lifecycle-model.md) · [architecture.md](./architecture.md)

## 愿景

建设 **AI 驱动的软件生命周期工厂** —— 一个能够理解软件项目在任何阶段的状态、并驱动 AI 员工持续把它推进到下一阶段的平台。它管理 AI 员工、组织软件生产流程、连接各种 Agent Runtime，覆盖从 Idea 到 Optimization 的完整软件生命周期。

## 定位

```
AI Software Factory = AI 软件生命周期工厂

不是 AI Coding Assistant      —— 不替代编码工具, 而是组织生产
不是自动生成代码的工具        —— 代码只是中间产物, 生命周期才是对象
不是聊天机器人 / 单个 Agent   —— 是管理 Agent 的工厂
```

对应传统软件体系:

| 传统 | AI Software Factory |
|:-----|:--------------------|
| Jira | Task Management |
| Jenkins | Workflow Engine |
| K8s Dashboard | Agent Management + Dashboard |
| Confluence | Knowledge System |
| CI/CD | Validation System |
| GitOps / CD 流水线 | Change Intelligence + Change Driven Workflow |

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

- **Workspace / Project** (Phase 6A): 多项目组织, 每项目独立仓库与定义。
- **Task / Workflow** (Phase 3-4): 任务状态机 + 声明式流程引擎 (feature-delivery / bug-fix / release 等内置定义)。
- **Agent / Assignment / Execution** (Phase 4B): 注册表、分配器、执行派发, 全链路事件审计。
- **Runtime Adapter** (Phase 4B1/4C1/5A1): 执行出口唯一, Hermes 适配器实跑, Catalog/Registry/Adapter 三层分离。
- **Validation** (Phase 3A/6D): L1 Factory / L2 Workflow / L3 Artifact / L4 Change, 独立于 Agent 的证据链验证。
- **Recovery** (Phase 4C3): checkpoint + 事件回放, 断点续跑不依赖对话记忆。
- **Dashboard / Metrics** (Phase 4C4/5B/6B): 16 个视图 + 项目维度指标聚合。
- **Git / Change Intelligence / Change Driven Workflow** (Phase 6C/6D/6E): git 只读接入、提交任务关联、L4 判定、触发器驱动 "提交即发布" 链式交付。

## 核心价值

1. **可管理** — 管理 AI 员工 (Agent) 的生命周期、职责、可靠性 (Agent Registry + Assignment)
2. **可观察** — 任何时刻知道每个任务/Agent/执行在做什么、进度、阻塞 (Event 唯一事实源 + Dashboard)
3. **可验证** — Agent 自报告 ≠ 完成, Validation L1-L4 结果 = 事实 (证据链可回查)
4. **可恢复** — 截断/失败从 checkpoint 回放续跑, 零丢失 (Recovery by replay)
5. **可替换** — 不绑定任何 Agent 框架, Runtime 可插拔 (Hermes/Claude Code/LangGraph/OpenHands...)
6. **可积累** — 知识沉淀 (ADR/缺陷/经验 = 企业资产), 指标驱动持续优化
7. **可复制** — 一套平台支持多项目并行 (markpad/scorepocket/timeon...), 任意阶段接入

## 用户

- **工程师** — CLI 主入口: 创建任务、跑流程、看状态、恢复断点
- **技术负责人** — Dashboard 观察工厂运行、Agent 健康、质量指标、变更流
- **管理层** — 项目进度、风险、交付质量总览 (Projects View + Metrics)

## 成功标准

- 一个任务从创建到交付全程可观察、可恢复、可验证
- 项目可带任意已有状态接入, 从当前节点继续推进而非重建
- 多项目并行生产, 知识跨项目复用
- 新 Runtime / 新角色 / 新 Skill / 新工作流声明式接入 (零核心代码改动)
- 自动化指标达标: first_attempt_success > 95%、path_errors = 0、human_intervention 最小化
- 变更可驱动交付: git 提交 → L4 验证 → 触发器 → 目标工作流 (提交即发布)
