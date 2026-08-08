# AI Software Factory — Lifecycle Model

> 版本: v1.2 | 日期: 2026-08-06 (v1.1) / 2026-08-08 (依 Reality Audit 校准)
> 状态: 评审确认 (12 阶段 + 4 类接入点) + Reality Audit 校准 — 阶段 1–5 已实现 (product 模块), 阶段 6–9 完整实现
> 关联文档: [vision.md](./vision.md) · [design-principles.md](./design-principles.md) · [architecture.md](./architecture.md) · [status.md](./status.md)
> 评审依据: [architecture-review-2026-08.md](./architecture-review-2026-08.md) §3/§4/§5/§6
> 校准依据: [architecture-reality-audit.md](./audit/architecture-reality-audit.md) (附录 A: product 501 测试 / understanding 699 行 / exec 12353 行)
>
> 本文档定义 AI Software Factory 覆盖的**完整软件生命周期** (12 阶段), 以及
> Factory 如何支持**从任意节点接入** —— 项目带任何已有状态进入工厂, 都能被
> 理解、被挂载、被继续推进。
>
> 定位 (评审 §1 确认): **AI 工作生命周期管理平台** —— 7 项核心价值:
> 管理项目上下文 · 理解项目当前状态 · 调度不同 AI 能力 · 管理任务生命周期 ·
> 保存过程和决策历史 · 支持人工审核节点 · 支持任何阶段接入。

---

## 1. 生命周期总览 (12 阶段确认)

```
Idea → Research → PRD → Design → Architecture → Task Planning
  → Development → Testing → Release → Deployment → Monitoring → Optimization
     ↘________________________________________________________________↗
                       (Optimization 产生新 Idea, 回路)
```

12 阶段与实现/规划的映射 (评审 §4 确认模型合理):

| # | 阶段 | 核心产物 | Factory 支撑 | 落地 |
|:-:|:-----|:---------|:-------------|:-----|
| 1 | Idea | 一句话目标 / 问题描述 | tasks, project, workspace | ✅ 已实现 (product 模块) |
| 2 | Research | 调研结论 / 可行性 | tasks, workflows, knowledge | ✅ 已实现 (product 模块) |
| 3 | PRD | 需求文档 / 验收标准 | tasks, validation (L1/L2) | ✅ 已实现 (product 模块) |
| 4 | Design | 方案 / 设计稿 | tasks, workflows (决策门), knowledge (ADR) | ✅ 已实现 (product 模块) |
| 5 | Architecture | 架构决策 / 模块划分 | workflows, knowledge (ADR), validation | ✅ 已实现 (product 模块) |
| 6 | Task Planning | 任务拆解 / 依赖 / 分配 | tasks (parent_id/dependencies), workflows, assignment | ✅ 已有 |
| 7 | Development | 代码变更 | assignment, execution, runtime + providers, git, exec | ✅ 已有 (exec 工程 Sprint 4/5) |
| 8 | Testing | 验证报告 / 证据链 | validation (L1–L4), metrics | ✅ 已有 |
| 9 | Release | 发布版本 / 变更集 | workflows (release), change, changeflow | ✅ 已有 |
| 10 | Deployment | 部署状态 | workflows (release), execution | ⬜ 未实现 (Phase 10 规划) |
| 11 | Monitoring | 运行指标 / 事件流 | dashboard, metrics, events | ⬜ 未实现 (Phase 10 规划) |
| 12 | Optimization | 改进项 / 新任务 | metrics, change, changeflow, knowledge | ✅ 已有 |

> 阶段 1–5 的产品化链路 (想法→需求→设计) 由 **product 模块** (Phase 9 落地,
> factory-core/product/ 4063 行, 501 测试) **已实现**: idea → market → product → prd →
> 人工批准 → ui → architecture → task 拆解, CLI `factory product` 17 命令。
> 阶段 6–9 的任务/工作流/执行/验证已实现。阶段 10–11 (部署/监控/运维) 仍未实现
> (仅 release workflow 步骤, 无 deploy/monitor/incident), 规划见 [roadmap.md](./roadmap.md) Sprint 9+。
> 产品判断 (是否值得做/批准/驳回) 永远是人, LLM/Factory 只产出候选与证据 (评审 §3 原则)。

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

按"项目当前状态", 所有接入点归纳为 **4 类** (见 §3): 想法 / 已有代码 /
开发中 / 生产。其中"开发中"已有完整实现, **"想法"已实现 (product 模块)**,
"已有代码"已实现 (understanding 模块), 仅"生产"仍由 Phase 10 规划承接
(评审 §4 接入点确认, Reality Audit 附录 A 校准)。

> **Git 可选 (评审 §5 确认)**: Core (task/workflow/execution/validation/event)
> **零 Git 依赖**; git 是**可选能力** —— 独立模块, 经 Skill/MCP/Integration
> 注册, change intelligence 经接口注入而非硬依赖。生命周期模型不绑定任何
> 版本控制系统。

## 3. 四类接入点 (评审确认)

### ① 想法阶段 (Idea) —— ✅ 已实现 (product 模块, Phase 9 落地)

- **输入**: 一个想法 (一句话目标 / 问题描述), 无任何工程产物。
- **输出**: 市场/竞品分析 → 结构化 PRD → UI 原型 → 架构方案 → 任务清单。
- **能理解什么**: 想法记录本身; 产品起点 (想法) 到任务定义之间的空白 —— 调研、
  PRD、UI、架构、任务拆解已由 product 模块覆盖 (idea → market → product → prd →
  approve → ui → architecture → task, CLI `factory product` 17 命令, 501 测试)。
- **缺什么**: 形式化的需求与验收标准; 产品决策 (是否值得做、批准/驳回) 永远归人。
- **如何继续**: product 模块把 Idea 推进到 Research (市场/竞品, 外部检索, 证据入事件库)
  → Product Analysis → PRD (结构化) → **[人工批准闸口]** → UI 原型 + 架构方案
  (候选产物, 不直接写码) → 任务拆解 (task.create 候选) → 人工确认 → 进入 ③/④
  工作流执行。人工批准复用既有 validate 退出码/三挡板语义; 接入方式与
  orchestration/changeflow 同模式 (新模块 + CLI 扩展 + Dashboard 视图 + 复用 Core API)。
- **对应生命周期**: 阶段 1–6 (Idea → Task Planning)。

### ② 已有代码 (存量项目) —— ✅ 已实现 (understanding 模块, Phase 7 落地)

- **输入**: 任意阶段的 git 仓库 (刚初始化 / 半成品 / 老项目), 无 Factory 配置。
- **输出**: **Understanding Report** —— 项目阶段判断 / 技术栈 / 架构形态 /
  产物完整度 / 缺失信息 / 风险 / 下一步建议; 可一键生成 ProjectConfig 草稿。
- **能理解什么**: 语言/技术栈、目录结构、包管理文件、README/文档、CI 配置、
  git 历史形态、已存在产物 (源码/测试/构建/部署清单) 的完整度 (understanding/
  699 行: inspection/detection/lifecycle/analysis/recommender)。
- **缺什么**: 项目尚未形式化进 Factory (无 project.yaml / 无任务 / 无验收标准)。
- **如何继续**: 采纳配置草稿 → 项目进入 Factory 管理 → 缺失信息以任务补齐
  (无测试→建测试任务, 无 README→建文档任务) → 按检测出的阶段
  (idea/scaffold/active-dev/stable/legacy/dead) 选择对应工作流继续。全程只读,
  不改写仓库 (零写命令铁律沿用 6C)。
- **对应生命周期**: 任意阶段进入, 通常落在 6–8 (Task Planning → Development → Testing)。

### ③ 开发中项目 —— ✅ 已有 (Core)

- **输入**: 任务定义 / 已有仓库 / 进行中的工作。
- **输出**: 继续 Task/Workflow 执行 —— 开发、验证、恢复、观测全链路。
- **能理解什么**: 任务的 scope 与验收标准、git 工作区状态 (status/diff)、提交
  历史与任务关联 (change commits: message > execution > branch 三来源解析)、
  执行进度 (checkpoint/事件流)。
- **缺什么**: 无 —— 这是 Factory 的执行核心 (任务生命周期完整闭环)。
- **如何继续**: `task create` 表达当前要推进的工作 → `execution run` 派发到
  Runtime Adapter → 变更检测与任务绑定 (`git.change.detected` /
  `git.task.bound`) → `validate` (L1–L4) → 截断可 `recover` 从 checkpoint 续跑;
  变更驱动工作流 (Phase 6E) 支持"修完→验证→发布"自动链。
- **对应生命周期**: 阶段 6–9 (Task Planning → Release)。

### ④ 生产系统 —— 落地: Phase 10 Operations

- **输入**: 已部署的服务 / 部署状态 / 运行事件。
- **输出**: Monitoring (健康检查/指标采集) / Alert (故障→事件流) /
  Maintenance (巡检工单) / AI 诊断建议 (建议模式)。
- **能理解什么**: Factory 侧的全部事件流与指标 (dashboard/metrics/events,
  生产过程可观测); release 工作流的部署留痕。
- **缺什么**: 应用自身的运行时遥测 (APM 等) —— Factory 观测的是**生产过程**,
  不是生产系统的内部指标; 真实环境部署执行器 (规划中)。
- **如何继续**: 部署动作封装为 workflow 步骤或 MCP 工具 → 健康检查 (只读探测,
  失败→结构化错误) → incident 创建 → AI 诊断 (复用 Recovery 回放思路) →
  **人工确认**处置 (破坏性操作默认禁止自动执行) → 维护巡检生成工单; 指标 →
  新任务回到 ① (闭环)。
- **对应生命周期**: 阶段 10–12 (Deployment → Monitoring → Optimization)。

## 4. 各阶段接入点 (12 阶段细化)

### 阶段 1 — Idea

- **Factory 能理解什么**: 项目存在性与技术栈 (project.yaml 的 name/tech_stack/language)、仓库是否已有内容 (git status)、工作区里有哪些项目 (workspace.projects)。
- **缺什么**: 目标还没有被形式化为需求与验收标准。
- **如何继续**: `task create --type feature` 把 Idea 表达为任务 (默认挂 feature-delivery 工作流); 若 Idea 需要先探索, 挂调研型 workflow, 由 Agent 装配对应 Skill 产出探索结论。Idea → Research 的推进完全可观察 (task.viewed/status 时间线)。**已实现**: 从一句话想法直接产出市场分析/PRD/UI/任务的产品化链路由 product 模块承接 (见 §3 ①, 501 测试)。

### 阶段 2 — Research

- **Factory 能理解什么**: 调研任务的进展 (task 状态机 + checkpoint)、Agent 调研产物 (execution 结果与 artifacts)、仓库现有文档作为上下文。
- **缺什么**: 调研结论尚未固化为"可验收的结论"。
- **如何继续**: 用 `validate` (L1/L2) 验证调研任务满足验收条件 (如结论文档存在、覆盖要求的问题清单); 结论沉淀进 knowledge/ 供后续 PRD 阶段检索复用。**已实现**: 外部检索 (市场/竞品) 由 product 模块 research 步骤承接, 数据源标注来源与时效。

### 阶段 3 — PRD

- **Factory 能理解什么**: 需求以任务形式存在 (title/type/acceptance), 仓库中已有文档即上下文。
- **缺什么**: 需求尚未拆解为可执行的工作项 (Factory 不替代产品经理产出 PRD 正文, 只管理其生命周期)。
- **如何继续**: PRD 文档作为产物挂到任务上; 验收标准 (acceptance) 进入任务定义, 成为后期 Validation 的输入 —— "验收标准先行"是 Factory 验证体系的天然要求 (L1 task_data / L2 workflow 规则)。**已实现**: product 模块生成结构化 PRD, 带**人工批准闸口** —— 未经用户批准的 PRD 不可能进入 UI/架构。

### 阶段 4 — Design

- **Factory 能理解什么**: 设计任务、设计产物 (文档/设计稿文件)、决策门要求 (无决策记录不进入开发)。
- **缺什么**: 设计方案的取舍判断 (这是产品/技术决策, 归人工, 见原则④)。
- **如何继续**: 走带**决策门**的 workflow; 设计评审由人批准 (approve/reject); 已定决策自动沉淀为知识 (ADR), 后续开发阶段可直接引用。**已实现**: product 模块的 UI 原型作为"候选产物"提交, 人工确认后才进入架构。

### 阶段 5 — Architecture

- **Factory 能理解什么**: 架构决策记录 (knowledge/adr)、模块划分 (可表达为任务依赖图: Task.parent_id / dependencies)、项目技术栈 (project.yaml → Skill 装配)。
- **缺什么**: 架构本身的权衡判断。
- **如何继续**: 架构任务走 workflow 的架构步骤 (如 desktop-feature 流程), 出口处决策门人工放行; 架构变更命中三挡板之一时 → `task.blocked` 上报, 人工裁决 (原则④)。**已实现**: product 模块的架构方案 → 自动拆解为任务清单, 人工确认后进入执行。

### 阶段 6 — Task Planning

- **Factory 能理解什么**: 任务拆解 (parent/sub 任务)、依赖关系 (dependencies)、流程步骤 (workflow steps)、谁适合做什么 (Agent Registry 角色 + Skill + 可靠性)。
- **缺什么**: 无 —— 这是 Factory 的强项区间。
- **如何继续**: `task create` 建父任务与子任务 → `workflow run` 启动流程 → `agent assign --step development` 自动匹配或显式指定 Agent (AgentAllocator), 分配结果发 `agent.assignment.created`。依赖不满足的步骤不会提前执行 (WorkflowEngine 步骤就绪检查)。

### 阶段 7 — Development

- **Factory 能理解什么**: 任务的 scope 与验收标准、git 工作区状态 (git status/diff)、提交历史与任务关联 (change commits: message > execution > branch 三来源解析)。
- **缺什么**: 无 —— 这是 Factory 的执行核心 (开发链路在 Sprint 4/5 得到大幅强化, 见下)。
- **如何继续**: `execution run` 派发执行到 Runtime Adapter (默认 Hermes, 可换; 真实 LLM 经 exec providers 适配器 → DeepSeek/Ollama, 见 [status.md](./status.md) 执行链路); 执行全链路事件 (`execution.started/completed/failed`、工具调用事件); 变更被检测并与任务绑定 (`git.change.detected` / `git.task.bound`); 截断可 `recover` 从 checkpoint 续跑。
- **exec 执行工程 (Sprint 4/5, Reality Audit 校准补充)**: 单 Agent 执行链已工程化 ——
  Context 装配 (6 类 Context + Ranking Top-K 6 因素 + Progressive 3 阶段加载 + Budget 4 任务类型)
  → DeveloperAgent (LLM→Operation→Patch, 沙箱副本) → MultiRun (N=3) → Evaluator (5 层确定性评估)
  → Experience 回写 (17 字段)。代码在 factory-exec (12353 行, 1019 测试)。
  **诚实标注**: 这是"执行工程", 不是"生产结果" — 真实 Benchmark (DeepSeek) 25/27 空响应,
  Bug Fix 0%, 见 [sprint5-t55-benchmark-report.md](./validation/sprint5-t55-benchmark-report.md)。
- **规划**: ② 已有代码接入在此汇合 —— understanding 模块产出 Understanding Report 后, 缺失信息补齐为任务, 即进入本阶段。

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
- **如何继续**: release workflow 的部署步骤执行并留痕; 部署结果作为事件进入时间线, 与 Monitoring 阶段衔接。接入深度可按项目演进: 把部署动作封装为 workflow 步骤或 MCP 工具, 无需改核心。**规划**: Phase 10 把 release 工作流延伸到部署 (构建 → 环境发布 → 回滚预案), 即 ④ 生产接入 (见 §3 ④)。

### 阶段 11 — Monitoring

- **Factory 能理解什么**: 全部事件流 (event logs, `--workspace` 跨项目)、Dashboard 16 视图、项目维度指标 (metrics --project / --workspace: 成功率、耗时、失败模式)。
- **缺什么**: 应用自身的运行时遥测 (APM 等) —— Factory 观测的是**生产过程**, 不是生产系统的内部指标。
- **如何继续**: `dashboard` 看工厂运行总览; `metrics` 聚合质量指标 (first_attempt_success / path_errors / human_intervention); `event logs` 追溯任何任务/执行/变更的完整证据链。**规划**: Phase 10 增加服务维度健康检查与指标采集 (只读探测)。

### 阶段 12 — Optimization

- **Factory 能理解什么**: 指标趋势、失败模式、知识沉淀 (knowledge/), 以及变更流里暴露的问题 (change analyze)。
- **缺什么**: 优化方向的业务判断。
- **如何继续**: 指标 → 新任务 (回到 Idea, 闭环); 重复失败自动提示沉淀经验; 变更驱动的触发器让"修完 → 验证 → 发布"全自动。Optimization 的输出是新的 Idea, 生命周期回到阶段 1。

## 5. 接入矩阵 (快速索引)

| 接入点 | 输入 | 输出 | 落地 | 能理解 | 缺 | 继续动作 |
|:-------|:-----|:-----|:----:|:-------|:---|:---------|
| ① 想法 | 一句话想法 | 市场分析/PRD/UI/架构/任务清单 | ✅ 已实现 (product 501) | 想法记录 + 产品化链路 | 形式化需求与验收标准 | 人工批准闸口 → 任务进入 ③/④ |
| ② 已有代码 | Git 仓库 (任意阶段) | Understanding Report (阶段/技术栈/架构/缺失/风险/建议) | ✅ 已实现 (understanding 699) | 仓库事实与产物完整度 | Factory 配置/任务化表达 | 采纳配置草稿 → 补缺失 → 继续开发 |
| ③ 开发中 | 任务/仓库 | 继续 Task/Workflow 执行 | ✅ 已有 (Core + exec) | 状态/提交/变更路径/执行进度 | 无 | change analyze → L4 → 开发/发布 |
| ④ 生产 | 服务/部署 | Monitoring/Alert/维护/诊断建议 | ⬜ 未实现 (Phase 10 规划) | 过程指标/证据链 | 运行时遥测/部署执行器 | 诊断建议 → 人工确认 → 巡检/回滚 |

## 6. 设计约束

1. **单点接入, 统一推进**: 无论从哪个阶段进入, 之后都收敛到同一套
   Workspace → Task → Workflow → Execution → Validation → Recovery 基础设施。
2. **阶段产物 = 证据**: 每个阶段的产物 (文档/代码/验证报告) 都挂在任务与事件
   上, 既是"能理解什么"的输入, 也是下一阶段的上下文。
3. **不伪造缺失阶段**: Factory 理解"缺什么"并显式补齐 (用任务/工作流), 从不
   假设某个阶段已经完成 —— 这正是 L1-L4 验证与决策门存在的原因。
4. **回路闭合**: Optimization 阶段的输出必须能回到 Idea 阶段 (指标 → 新任务),
   否则工厂是流水线而不是生命周期。
5. **Core 零 Git 依赖 (评审 §5 新增)**: Git 是可选能力 —— git/ 独立模块,
   change intelligence 经接口注入; 生命周期模型不绑定任何版本控制系统。
6. **人类审核是价值而非附加**: 三挡板/决策门/人工批准闸口是生命周期的一部分,
   每个决策点可查看、可批准、可驳回 (未来由 Human Approval Console 统一承载, 见 roadmap Phase 11)。
