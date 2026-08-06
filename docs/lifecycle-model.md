# AI Software Factory — Lifecycle Model

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 与 Phase 6E 实现对齐
> 关联文档: [vision.md](./vision.md) · [design-principles.md](./design-principles.md) · [architecture.md](./architecture.md)
>
> 本文档定义 AI Software Factory 覆盖的**完整软件生命周期** (12 阶段), 以及
> Factory 如何支持**从任意节点接入** —— 项目带任何已有状态进入工厂, 都能被
> 理解、被挂载、被继续推进。

---

## 1. 生命周期总览

```
Idea → Research → PRD → Design → Architecture → Task Planning
  → Development → Testing → Release → Deployment → Monitoring → Optimization
     ↘________________________________________________________________↗
                       (Optimization 产生新 Idea, 回路)
```

| # | 阶段 | 核心产物 | Factory 支撑模块 |
|:-:|:-----|:---------|:-----------------|
| 1 | Idea | 一句话目标 / 问题描述 | tasks, project, workspace |
| 2 | Research | 调研结论 / 可行性 | tasks, workflows, knowledge |
| 3 | PRD | 需求文档 / 验收标准 | tasks, validation (L1/L2) |
| 4 | Design | 方案 / 设计稿 | tasks, workflows (决策门), knowledge (ADR) |
| 5 | Architecture | 架构决策 / 模块划分 | workflows, knowledge (ADR), validation |
| 6 | Task Planning | 任务拆解 / 依赖 / 分配 | tasks (parent_id/dependencies), workflows, assignment |
| 7 | Development | 代码变更 | assignment, execution, runtime (Hermes), git |
| 8 | Testing | 验证报告 / 证据链 | validation (L1-L4), metrics |
| 9 | Release | 发布版本 / 变更集 | workflows (release), change, changeflow |
| 10 | Deployment | 部署状态 | workflows (release), execution |
| 11 | Monitoring | 运行指标 / 事件流 | dashboard, metrics, events |
| 12 | Optimization | 改进项 / 新任务 | metrics, change, changeflow, knowledge |

## 2. 核心命题: 任意节点接入

Factory 不要求项目从 Idea 开始。**项目在哪个阶段, 就从哪个阶段进入**:

> Factory 对任意接入点做三件事:
> 1. **理解** — 读取该阶段已存在的证据 (仓库、文档、git 历史、事件流、指标)
> 2. **补全** — 识别缺失的上下文, 用任务/工作流补齐
> 3. **继续** — 沿生命周期向前推进, 而不是重建

接入的物理动作是统一的: `workspace init` 挂载工作区 → `project` 层关联真实仓库
(project.yaml: name/language/repository/tech_stack) → `task create` 表达当前要
推进的工作 → `workflow` 选择从当前节点开始的路径 → 之后的 Development/Testing/
Release 完全复用同一套执行-验证-恢复-观测基础设施。

## 3. 各阶段接入点

### 阶段 1 — Idea

- **Factory 能理解什么**: 项目存在性与技术栈 (project.yaml 的 name/tech_stack/language)、仓库是否已有内容 (git status)、工作区里有哪些项目 (workspace.projects)。
- **缺什么**: 目标还没有被形式化为需求与验收标准。
- **如何继续**: `task create --type feature` 把 Idea 表达为任务 (默认挂 feature-delivery 工作流); 若 Idea 需要先探索, 挂调研型 workflow, 由 Agent 装配对应 Skill 产出探索结论。Idea → Research 的推进完全可观察 (task.viewed/status 时间线)。

### 阶段 2 — Research

- **Factory 能理解什么**: 调研任务的进展 (task 状态机 + checkpoint)、Agent 调研产物 (execution 结果与 artifacts)、仓库现有文档作为上下文。
- **缺什么**: 调研结论尚未固化为"可验收的结论"。
- **如何继续**: 用 `validate` (L1/L2) 验证调研任务满足验收条件 (如结论文档存在、覆盖要求的问题清单); 结论沉淀进 knowledge/ 供后续 PRD 阶段检索复用。

### 阶段 3 — PRD

- **Factory 能理解什么**: 需求以任务形式存在 (title/type/acceptance), 仓库中已有文档即上下文。
- **缺什么**: 需求尚未拆解为可执行的工作项 (Factory 不替代产品经理产出 PRD 正文, 只管理其生命周期)。
- **如何继续**: PRD 文档作为产物挂到任务上; 验收标准 (acceptance) 进入任务定义, 成为后期 Validation 的输入 —— "验收标准先行"是 Factory 验证体系的天然要求 (L1 task_data / L2 workflow 规则)。

### 阶段 4 — Design

- **Factory 能理解什么**: 设计任务、设计产物 (文档/设计稿文件)、决策门要求 (无决策记录不进入开发)。
- **缺什么**: 设计方案的取舍判断 (这是产品/技术决策, 归人工, 见原则④)。
- **如何继续**: 走带**决策门**的 workflow; 设计评审由人批准 (approve/reject); 已定决策自动沉淀为知识 (ADR), 后续开发阶段可直接引用。

### 阶段 5 — Architecture

- **Factory 能理解什么**: 架构决策记录 (knowledge/adr)、模块划分 (可表达为任务依赖图: Task.parent_id / dependencies)、项目技术栈 (project.yaml → Skill 装配)。
- **缺什么**: 架构本身的权衡判断。
- **如何继续**: 架构任务走 workflow 的架构步骤 (如 desktop-feature 流程), 出口处决策门人工放行; 架构变更命中三挡板之一时 → `task.blocked` 上报, 人工裁决 (原则④)。

### 阶段 6 — Task Planning

- **Factory 能理解什么**: 任务拆解 (parent/sub 任务)、依赖关系 (dependencies)、流程步骤 (workflow steps)、谁适合做什么 (Agent Registry 角色 + Skill + 可靠性)。
- **缺什么**: 无 —— 这是 Factory 的强项区间。
- **如何继续**: `task create` 建父任务与子任务 → `workflow run` 启动流程 → `agent assign --step development` 自动匹配或显式指定 Agent (AgentAllocator), 分配结果发 `agent.assignment.created`。依赖不满足的步骤不会提前执行 (WorkflowEngine 步骤就绪检查)。

### 阶段 7 — Development

- **Factory 能理解什么**: 任务的 scope 与验收标准、git 工作区状态 (git status/diff)、提交历史与任务关联 (change commits: message > execution > branch 三来源解析)。
- **缺什么**: 无 —— 这是 Factory 的执行核心。
- **如何继续**: `execution run` 派发执行到 Runtime Adapter (默认 Hermes, 可换); 执行全链路事件 (`execution.started/completed/failed`、工具调用事件); 变更被检测并与任务绑定 (`git.change.detected` / `git.task.bound`); 截断可 `recover` 从 checkpoint 续跑。

### 阶段 8 — Testing

- **Factory 能理解什么**: 任务是否满足验收标准、流程是否走完、产物是否存在于预期路径、变更是否与任务描述一致。
- **缺什么**: 无 —— 验证独立于执行者是 Factory 的核心公理。
- **如何继续**: `validate <task>` 四层验证:
  - **L1 Factory**: 任务存在/数据完整/状态合法/文件在预期绝对路径
  - **L2 Workflow**: 流程步骤与期望状态核对
  - **L3 Artifact**: 产物钩子检查
  - **L4 Change**: 任务描述 vs git 变更证据 (Phase 6D, 确定性规则, 禁 LLM)
  结论 = PASS/FAIL/SKIP/ERROR + 证据链 (`validation.rule.*` 事件, 退出码 0/3/1/7), 证据落 validation/artifacts/。

### 阶段 9 — Release

- **Factory 能理解什么**: 变更集 (change analyze: Files/Insertions/Deletions/Modules)、L4 验证结论、内置 release 工作流 (含 ops-engineer 角色步骤)。
- **缺什么**: 发布策略本身 (哪些变更进哪个版本) 是产品决策。
- **如何继续**: 两种路径 —— ① `workflow run release` 手动发布; ② **Change Driven Workflow** (Phase 6E): 注册触发器 (`change triggers register --target-workflow release`), 任务验证 PASS 且规则 (validation.l4 / commit.linked / required.files / runtime.pref) 满足 → `change evaluate` PASS → 自动启动 release run, 形成"提交即发布"链式交付; `change workflows` 查看完整工作流链。

### 阶段 10 — Deployment

- **Factory 能理解什么**: release 工作流的执行状态 (workflow run/step 事件)、部署相关步骤的产物、执行记录。
- **缺什么**: 真实环境的部署执行器 (第一版部署步骤由 release workflow 内的人工/脚本步骤完成, 未接入具体云平台)。
- **如何继续**: release workflow 的部署步骤执行并留痕; 部署结果作为事件进入时间线, 与 Monitoring 阶段衔接。接入深度可按项目演进: 把部署动作封装为 workflow 步骤或 MCP 工具, 无需改核心。

### 阶段 11 — Monitoring

- **Factory 能理解什么**: 全部事件流 (event logs, `--workspace` 跨项目)、Dashboard 16 视图、项目维度指标 (metrics --project / --workspace: 成功率、耗时、失败模式)。
- **缺什么**: 应用自身的运行时遥测 (APM 等) —— Factory 观测的是**生产过程**, 不是生产系统的内部指标。
- **如何继续**: `dashboard` 看工厂运行总览; `metrics` 聚合质量指标 (first_attempt_success / path_errors / human_intervention); `event logs` 追溯任何任务/执行/变更的完整证据链。

### 阶段 12 — Optimization

- **Factory 能理解什么**: 指标趋势、失败模式、知识沉淀 (knowledge/), 以及变更流里暴露的问题 (change analyze)。
- **缺什么**: 优化方向的业务判断。
- **如何继续**: 指标 → 新任务 (回到 Idea, 闭环); 重复失败自动提示沉淀经验; 变更驱动的触发器让"修完 → 验证 → 发布"全自动。Optimization 的输出是新的 Idea, 生命周期回到阶段 1。

## 4. 接入矩阵 (快速索引)

| 接入点 | 挂载动作 | Factory 能理解 | 缺 | 继续动作 |
|:-------|:---------|:---------------|:---|:---------|
| Idea | workspace/project + task create | 项目/技术栈/仓库 | 形式化需求 | 调研或开发工作流 |
| PRD | task create + 验收标准 | 需求描述/文档上下文 | 工作项拆解 | Task Planning |
| Design | workflow + 决策门 | 设计产物/决策记录 | 取舍判断 (人工) | 批准后进开发 |
| 开发中代码 | workspace 挂载 + git | 状态/提交/变更路径 | 任务化表达 | change analyze → L4 → 开发 |
| 存量代码 | project.yaml + Skill 装配 | 技术栈 → 角色/技能 | 上下文注入 | 按角色分派 |
| 生产系统 | 事件流 + metrics | 过程指标/证据链 | 运行时遥测 | Monitoring → Optimization |

## 5. 设计约束

1. **单点接入, 统一推进**: 无论从哪个阶段进入, 之后都收敛到同一套
   Workspace → Task → Workflow → Execution → Validation → Recovery 基础设施。
2. **阶段产物 = 证据**: 每个阶段的产物 (文档/代码/验证报告) 都挂在任务与事件
   上, 既是"能理解什么"的输入, 也是下一阶段的上下文。
3. **不伪造缺失阶段**: Factory 理解"缺什么"并显式补齐 (用任务/工作流), 从不
   假设某个阶段已经完成 —— 这正是 L1-L4 验证与决策门存在的原因。
4. **回路闭合**: Optimization 阶段的输出必须能回到 Idea 阶段 (指标 → 新任务),
   否则工厂是流水线而不是生命周期。
