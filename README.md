# AI Software Factory

> **AI 工作生命周期管理平台** — 管理 AI 员工 (Agent)、组织软件生产流程 (Workflow)、连接各种 Agent Runtime 与 LLM Provider, 让一个软件项目从 Idea 到交付/运维的**全生命周期**处于可管理、可观察、可验证、可积累的状态。
>
> 不是聊天机器人, 不是单个 Agent, 不是代码生成工具 — 是**管理 Agent 的工厂**。
> 类比: Jira (任务) + Jenkins (流程) + K8s Dashboard (可观测) + Confluence (知识) + CI/CD (验证) 的 AI 时代对应。

---

## Vision — 为什么存在

> **"AI Software Factory is not a tool that generates software. It is a system that grows with capabilities and helps humans accomplish goals."**
>
> **AI Software Factory 不是生成软件的工具, 而是一个能力持续生长的系统, 帮助人类达成目标。**

软件生产正在从"靠人盯着 AI 干活"升级为工厂化运转。Factory 的存在不是为了替人写代码 —— 写代码只是中间产物。它的对象是**工作的生命周期**: 一个想法如何被调研、被写成需求、被批准、被架构、被开发、被验证、被运维, 以及这些过程如何沉淀为下一次做得更好的经验。

一句话: **传统 AI Coding 是"问答", Factory 是"生产线 + 记忆 + 成长"。**

## Problem — 传统 AI Coding 的局限

传统 AI Coding 是 `User → Prompt → Code` 的单次问答模式。它把 AI 当成一个"即用即走"的代码生成器, 这带来五个根本局限:

| # | 局限 | 后果 |
|:-:|:-----|:-----|
| 1 | **无长期记忆** | 每次会话从零开始: 项目上下文、历史决策、进行中状态全部丢失, 换个会话就"失忆", 工作无法延续 |
| 2 | **无经验积累** | 成功、失败、用户反馈都不会沉淀: 同样的坑反复踩, 团队无法从历史中变强, 能力永远停在原地 |
| 3 | **无能力评估** | 不知道该用哪个模型/Agent 做哪类任务: 选择全凭感觉, 性能、成本、匹配度不可见、不可比较 |
| 4 | **无决策透明** | AI 只给结果不给解释: 为什么这么做不可追溯、不可审计, "完成了"是自报告, 没有独立验证 |
| 5 | **无法组织生产** | 单点问答支撑不了多角色协作、多项目并行、长流程编排与人工审核 —— 更不用说把生产经验沉淀为资产 |

结果是: AI 能力越强, 人越累 —— 因为所有上下文、判断、验收、记忆都压在人身上。

## Solution — 从"问答"到"持续成长的生命周期系统"

Factory 把软件生产组织成一条**可管理的生命周期链**, 并把每个环节的产物变成下一环节的证据:

```
Idea → Research → PRD → Approval → Architecture → Development → Testing → Operation → Experience
   ▲                                                                                        │
   └────────────────────────── 经验回流, 指导下一次选择 ──────────────────────────────────────┘
```

(浓缩自 12 阶段生命周期模型, 见 [docs/lifecycle-model.md](./docs/lifecycle-model.md))

- **Idea / Research / PRD** — Product Intelligence (Phase 9) 承接: 想法 → 调研 → 结构化 PRD, 产物作为证据进入事件库
- **Approval** — 产品决策的闸口在人: Approval 状态机 + Decision 链 + 人类审核台 (Phase 9c / 11), AI 只产出候选与建议
- **Architecture** — 架构方案与任务拆解作为候选产物提交, 人工确认后进入开发
- **Development / Testing** — 工厂的核心执行域: 任务状态机、声明式工作流、角色化 Agent、Runtime 执行、L1–L4 独立验证、checkpoint 恢复, 全程事件可追溯
- **Operation** — 发布工作流 + 生产过程可观测 (事件流/Dashboard/指标); 部署执行器与运维闭环规划中
- **Experience** — 成功/失败/反馈全部记录为经验 (Phase 10A), 经验经推荐引擎**影响但不支配**未来的 Provider/Agent/Workflow 选择

三个关键性质, 使它与"问答式 AI Coding"根本不同:

1. **任意阶段接入** — 项目带任何已有状态进入 (只有一个想法 / 已有代码 / 开发中 / 生产), 从当前节点继续推进, 而不是重建
2. **能力持续生长** — 新能力以 Extension 声明式注册 (新 Skill / MCP / Runtime / Provider / 工作流), 零核心破坏, 系统越用越强
3. **经验是资产** — 失败记录不是污点而是最贵的工程资产, 与成功记录一样被沉淀、被衰减、被复用

## Core Philosophy — 四条核心理念

### ① Professional does professional work — 专业的人做专业的事

同一平台上, 架构师用擅长推理的模型、开发者用擅长写码的 Agent、测试员用擅长验证的 Runtime —— 平台按 **Capability / Cost / Performance / Experience** 四因素 (权重 0.35 / 0.30 / 0.20 / 0.15) 为每个任务选出**最合适的执行资源** (Provider / Agent / Skill / Workflow), 而不是让一个模型干所有事。选谁、为什么选它, 都有结构化解释, 任何人都能复算。

### ② Human in the loop — 人在环上, 决策权在人

**AI 负责分析、推荐、解释; 人负责决策、批准、负责。** 平台"只推荐不自动执行" —— 高风险推荐必须经人工审批 (Approval 状态机), 产品冲突、架构变更、Scope 扩展三类挡板命中即暂停上报。Human Console (Web UI 人类审核台) 给人看状态、看推荐理由、批准或驳回。自动化可以提速, 但**不能静默改变产品方向**。

### ③ Evidence driven — 一切以证据为准

**Agent 自报告 ≠ 完成。** 交付是否完成由独立的 Validation 引擎 (L1–L4) 判定, 结论 = PASS/FAIL/SKIP/ERROR + 证据链; 每个推荐与决策都附 Evidence 链 (六来源: artifact / event / experience / external_data / human_input / provider_output)、Confidence 置信度与逐条 Reasoning 解释。事实优先级最高, AI 输出是建议不是依据 —— 可追溯、可审计、可证伪。

### ④ Experience accumulation — 成功、失败、反馈都成经验

每次执行的成败、用户的反馈、决策的后果, 都以经验记录沉淀 (五域: provider / agent / workflow / project / decision, 含反事实的失败样本)。经验带**新鲜度衰减** (半衰期 30 天, 被验证的经验保持有效), 经推荐引擎影响未来的选择, 但**绝不支配** (冷启动给中性分, 不惩罚新候选)。工厂不是用过即弃的工具, 而是越用越懂你的系统。

---

## Architecture — 一句话

**三区架构 (2026-08 冻结)**: **Core** (12 项通用原语: 事件/任务/工作流/Agent/Runtime/验证/恢复/观测/指标等, 零领域依赖) + **Extension** (Git/Change/Understanding/Provider/Product/Intelligence 等能力一律声明式注册, 不修改 Core) + **Human Layer** (Approval Console Web UI 人类审核台, 只读 + 审批动作)。

- 统一抽象: `Agent (角色) ── Skills (能力) ── MCP (工具) ── Runtime (执行) ── Provider (LLM)` — 上层编排不关心底层 AI 是谁, 换工具 = 改配置
- 事件是唯一事实源 (append-only SQLite, 可回放重建状态); 恢复 = checkpoint + 事件回放, 断点续跑零丢失
- 设计原则 9 条 (事件唯一事实源 / 一切可观测 / AI 可替换 / 人类审核台 / 三层分离 / 恢复=回放 / 增量演进零破坏 / Git 可选 / 任意阶段接入): [docs/design-principles.md](./docs/design-principles.md)

## Status — 现状

- **交付**: Phase 1–6E (核心执行闭环) + Phase 7 (Project Understanding) + Phase 8 (LLM Provider 抽象) + Phase 9 (Product Intelligence + 人工决策) + Phase 10A (Intelligence Layer: Decision / Recommendation / Experience) + Phase 11 (Human Console API + Web UI), **41 次提交**, 每阶段独立可交付、可回退
- **测试**: **4090 pytest 全绿** (EventType 纯增量扩展, 基线只增不减) + 92 Vitest (Web UI)
- **决策记录**: ADR-0001–0035 (docs/adr/), 设计文档齐全 (docs/vision.md · design-principles.md · lifecycle-model.md · capability-architecture.md · roadmap.md 等)
- **规模**: CLI 20+ 命令组 · Dashboard 20 视图 · 六域指标 · 12 阶段生命周期中 6–9 (Task Planning→Release) 完整实现, 1–5 由 Product Intelligence 承接, 10–11 (Deployment/Monitoring) 部分支撑

## Quick Start

```bash
# 1. 安装 (Python 3.12+)
python3.12 -m venv .venv
.venv/bin/pip install -e .

# 2. 初始化工厂 (目录骨架 + 事件库, 幂等)
.venv/bin/factory init

# 3. 定义任务
.venv/bin/factory task create --id T-001 --title "实现登录页"

# 4. 自动执行完整链路 (工作流 → 匹配 Agent → 执行 → 验证)
.venv/bin/factory workflow run T-001 --auto

# 5. 观察工厂
.venv/bin/factory dashboard --view all
```

> 首次自动执行前需先注册 Agent 与 Runtime (`factory agent add` / `factory runtime add`), 完整命令参考: `factory --help`、[docs/vision.md](./docs/vision.md) 与 [docs/use-cases.md](./docs/use-cases.md)。

## 应用场景

一个人拥有 AI 软件团队 · 创业团队快速验证产品 · 企业研发部门管理多个 AI Agent · 外包团队自动化项目生命周期 · AI Agent 平台基础设施 — 见 **[docs/use-cases.md](./docs/use-cases.md)** (5 个场景: 痛点 / Factory 如何解决 / 示例流程)。

---

*文档: [docs/vision.md](./docs/vision.md) (愿景) · [docs/design-principles.md](./docs/design-principles.md) (9 原则) · [docs/lifecycle-model.md](./docs/lifecycle-model.md) (12 阶段生命周期) · [docs/capability-architecture.md](./docs/capability-architecture.md) (能力架构) · [docs/roadmap.md](./docs/roadmap.md) (路线图) · [docs/use-cases.md](./docs/use-cases.md) (应用场景) · [docs/adr/](./docs/adr/) (决策记录)*
