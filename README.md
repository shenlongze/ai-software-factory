# AI Software Factory

> **AI 工作生命周期管理平台** — 管理 AI 员工 (Agent)、组织软件生产流程 (Workflow)、连接各种 Agent Runtime, 让一个软件项目从 Idea 到交付/运维的**全生命周期**处于可管理、可观察、可验证、可积累的状态。
> 不是聊天机器人, 不是单个 Agent, 不是代码生成工具 — 是管理 Agent 的工厂。
> 类比: Jira (任务) + Jenkins (流程) + K8s Dashboard (可观测) + Confluence (知识) + CI/CD (验证) 的 AI 时代对应。

## Vision

让软件生产从"靠人盯着 AI 干活"升级为**可管理、可观察、可验证、可恢复、可替换、可积累、可复制**的工厂化运转:

1. **可管理** — 管理项目上下文: Event 流是唯一事实源, 任何状态变化都可追溯
2. **可观察** — 理解项目当前状态: Git/Change/Validation 证据链, 任何时刻知道每个 Agent/任务/执行在做什么
3. **可验证** — Agent 自报告 ≠ 完成, Validation L1–L4 结果才是事实
4. **可恢复** — 截断/失败从 checkpoint + 事件回放续跑, 零丢失
5. **可替换** — 不绑定任何单一 AI: Agent / Skill / MCP / Runtime / LLM Provider 统一抽象, 声明式接入
6. **可积累** — 架构决策 / 缺陷 / 经验沉淀为企业资产, 指标驱动持续优化
7. **可复制** — 一套平台支持多项目并行生产, 项目可带任意已有状态接入

**统一抽象模型** — 平台围绕一套稳定的概念模型组织, 上层编排不关心底层 AI 是谁:

```
Agent (角色) ── Skills (能力)
     │
     ├── MCP Tools (外部工具: GitHub/Jira/Figma/AWS)
     │
     └── Runtime (执行方式: Hermes / Codex / Claude / Local)
             │
             └── LLM Provider (Phase 8 规划: 解除单一绑定, 可插拔)
```

| 抽象 | 当前实现 | 状态 |
|:-----|:---------|:----:|
| **Agent 角色** | AgentRegistry (role / skills / status) | ✅ 已实现 |
| **Skills 能力** | SkillRegistry (category / capabilities) | ✅ 已实现 |
| **Runtime 执行** | RuntimeAdapter (echo / hermes) + Catalog/Registry/Adapter 三层分离 | ✅ 已实现 (per-agent runtime 偏好字段已建) |
| **MCP 工具** | mcp/ 目录占位 | 🚧 规划中 |
| **LLM Provider** | 当前唯一真实实现 HermesRuntimeAdapter | 🚧 Phase 8 核心 |

**Git 是可选能力**: Core (task / workflow / execution / validation) 零 Git 依赖; git/ 独立模块, change/changeflow 经接口接入 — 未来可注册为 Skill/MCP/Integration。

**成功标准**: 一个任务从创建到交付全程可观察、可恢复、可验证; 多项目并行生产、知识跨项目复用; 新 Runtime / 角色 / Skill / Provider 声明式接入 (零核心代码改动); 指标达标 (first_attempt_success > 95%, path_errors = 0, human_intervention 最小化)。

## Current Capability

已完成 12 项核心能力 (全部经 pytest 验证):

| # | 能力 | 说明 |
|:-:|:-----|:-----|
| 1 | **Workspace** | 多项目工作区 — workspace.yaml 管理、managed/示例项目自动发现、项目级数据隔离 |
| 2 | **Task Management** | 任务状态机 + JSON 持久化 + 事件时间线 + 项目归属 |
| 3 | **Workflow Engine** | 声明式多步工作流 + 状态机 + 内置定义 (feature-delivery / desktop-feature / bug-fix / release) |
| 4 | **Agent System** | Agent / Skill 注册表 + 角色/技能匹配 (Matcher) + 分配生命周期 (Allocator) + 状态追踪 |
| 5 | **Runtime Adapter** | 统一 Runtime 抽象 + 执行分派/运行 (Dispatcher / Runner / Service) + 内置 echo / hermes 适配器 + Runtime 能力目录 (Catalog) |
| 6 | **Hermes Integration** | HermesRuntimeAdapter 子进程接入 (FACTORY_HERMES_CMD / FACTORY_HERMES_TIMEOUT 可配置) |
| 7 | **Validation Engine (L1–L4)** | 四层验证: L1 基础 / L2 结构 / L3 行为 / L4 Change 语义, 规则可插拔 |
| 8 | **Recovery** | Checkpoint 快照 + EventReplay 断点恢复 (四场景: 运行中工作流/执行/Agent/已完成) |
| 9 | **Dashboard (16 视图)** | Rich 只读仪表盘: 总览/任务/Agent/工作流/执行/恢复/指标/目录/项目/工作区/Git/Change/Change Flow... |
| 10 | **Metrics** | 六域指标: 任务/执行/Agent/工作流/验证/失败 (first_attempt_success_rate 等) |
| 11 | **Git Intelligence** | Git 只读 + 审计: status/diff/commits + task↔commit 自动关联 (可选能力, Core 零依赖) |
| 12 | **Change Workflow** | 变更驱动工作流: commit 解析 → 变更分析 → L4 验证 → ChangeTrigger 规则引擎 → 自动触发工作流 |

## Architecture

```
                            ┌──────────────────────────────────────────────┐
                            │  CLI (argparse) —  factory <command>          │
                            │  init task event status validate agent skill  │
                            │  workflow runtime execution checkpoint        │
                            │  recover dashboard metrics project workspace  │
                            │  git change                                   │
                            └───────────────────┬──────────────────────────┘
                                                │
        ┌───────────────────────────────────────┼───────────────────────────────────────┐
        │            组合根 (只装配现有模块, 不重新实现)                                    │
        │    orchestration.pipeline · ChangeWorkflowEngine · RecoveryService             │
        └──────┬───────────┬───────────┬─────────────┬────────────┬───────────┬──────────┘
               │           │           │             │            │           │
     ┌─────────▼───┐ ┌─────▼────┐ ┌───▼──────┐ ┌─────▼─────┐ ┌───▼─────┐ ┌───▼────────┐
     │ 管理域       │ │ 执行域    │ │ 验证域    │ │ 观察域     │ │ 集成域   │ │ 组织域      │
     │ tasks       │ │ runtime  │ │ validation│ │ events    │ │ git     │ │ project    │
     │ workflows   │ │ runtimes │ │ change   │ │ metrics   │ │ changeflow│ │ workspace  │
     │ agents      │ │ execution│ │          │ │ dashboard │ │         │ │            │
     │ assignment  │ │          │ │          │ │ recovery  │ │         │ │            │
     └──────┬──────┘ └────┬─────┘ └────┬─────┘ └────┬──────┘ └────┬─────┘ └────┬───────┘
            │             │            │            │             │            │
     ┌──────▼─────────────▼────────────▼────────────▼─────────────▼────────────▼───────┐
     │ 存储层: SQLite (events — append-only 唯一事实源) + JSON 状态文件 (.factory/)      │
     │         单进程 · 零 ORM · 原子写 (tmp + os.replace) · Pydantic v2 模型           │
     └──────────────────────────────────────────────────────────────────────────────────┘
```

- **入口**: `factory` CLI (argparse), 18 组命令, 每次调用必发审计 Event (工程师主入口)
- **组合根**: 编排/恢复/变更触发等跨域流程只做装配, 不复制领域逻辑
- **域模块**: 每个包只干一件事 (KISS), 读写分离 — 观察域与集成域只读不写状态
- **统一抽象**: Agent = Skills + MCP + Runtime; 上层 Orchestration 只面向抽象, 不绑定具体 AI 框架
- **存储**: 事件走 SQLite (append-only, 可回放重建状态); 状态走 JSON (原子写, 损坏即报错不静默)
- **Git 可选**: git/change/changeflow 是独立集成域, Core 零 Git 依赖

## Current Status

- **20 个 Phase 全部交付** (Phase 0 设计稿 → Phase 1 观察层 → ... → Phase 6E Change Driven Workflow), 每条主线独立可交付、可回退
- **2159 tests 全绿, 零核心破坏** — EventType 纯增量扩展 (ADR-0001), 每阶段基线只增不减
- **ADR 决策记录 0001–0020** (docs/adr/), 设计文档齐全 (docs/design/, docs/vision.md, docs/roadmap.md, docs/lifecycle-model.md)
- 技术栈: **Python 3.12+ / Pydantic v2 / SQLite (事件) / JSON (状态) / Rich (Dashboard) / argparse (CLI) / PyYAML (示例配置)** — 单进程, 零数据库 ORM

## Future Roadmap

| 方向 | 目标 |
|:-----|:-----|
| **Project Understanding** (Phase 7) | 项目理解 — 输入任意 git 仓库, 自动产出事实清单/阶段判定/缺失分析/下一步建议, 从静态示例配置升级为运行时理解项目 |
| **LLM Provider** (Phase 8) | LLM 提供方抽象 — LLM Interface 协议 + 可插拔 Providers (Hermes / Codex / OpenAI 兼容 / Claude / Local), 解除 Hermes 单一绑定, 核心零改动 |
| **Product Intelligence** (Phase 9) | 产品智能 — Idea → Research → PRD → [人工批准] → UI/架构 → 任务拆解, 复用 Core 原语 (task/workflow/event/validation) |
| **Operations** (Phase 10) | 运营闭环 — 部署/监控/健康检查/故障诊断/巡检, 运维动作与开发一样可审计、可回放、可恢复 (默认建议模式, 破坏性操作必须人工确认) |
| **Human Approval Console** (Web UI) | 人类审核台 — Factory API (FastAPI 薄层: 只读 + 审批动作) → Core; Frontend (React/Vue 或轻量 HTML+JS)。给**人**审核用: 查看状态 / 审核 AI 输出 / 确认 PRD / 确认 UI / 审核执行 / 查看 Metrics。CLI 保留为工程师主入口 |

> 路线图原则: Core 提供通用原语 (Task/Workflow/Event/Validation), 新 Layer 是使用原语的高层编排 — 不破坏 Core; 人工审核节点 (三挡板 / validate 退出码) 语义贯穿始终。

## Quick Start

```bash
# 1. 安装 (Python 3.12+)
python3.12 -m venv .venv
.venv/bin/pip install -e .

# 2. 初始化工厂 (目录骨架 + 事件库, 幂等)
.venv/bin/factory init

# 3. 创建任务
.venv/bin/factory task create --id T-001 --title "实现登录页"

# 4. 注册编排前置: 内置工作流 + 匹配 Agent + Runtime
.venv/bin/factory workflow add --id feature-delivery
.venv/bin/factory agent add --id pm-1 --role product-manager --skills architecture
.venv/bin/factory agent add --id dev-1 --role backend-developer --skills development,python
.venv/bin/factory agent add --id test-1 --role test-engineer --skills testing,validation
.venv/bin/factory runtime add --id echo --type mock

# 5. 自动执行完整链路 (架构 → 开发 → 测试 → 独立验收)
.venv/bin/factory workflow run T-001 --auto
```

常用命令: `factory status` (工厂总览) · `factory event logs` (事件时间线) · `factory validate T-001` (L1–L4 验证) · `factory dashboard --view all` (16 视图仪表盘) · `factory metrics` (六域指标) · `factory git status` / `factory change analyze T-001` (变更智能) · `factory workspace init` (多项目管理)。全部命令支持 `--json`。

## Design Philosophy

七大设计原则, 全部来自 MarkPad 实战的实证教训 (docs/design/architecture.md §0):

1. **KISS — 最小模块集** — 每个模块只干一件事
2. **Orchestrator 不写代码** — 管理层只决策、委派、验收
3. **一切以事件为中心** — 任何状态变化都落事件流, 事件 = 唯一事实源
4. **自报告不可信, 验证独立** — Agent 说的不算, 验证引擎说了算
5. **文件即事实** — 文件范围声明 + 锁 + 校验, 杜绝越权写
6. **可断点续传** — 任何时刻可中断、可恢复
7. **人只出现在少数闸口** — 产品冲突 / 架构变更 / Scope 扩展才暂停 (三挡板 / Decision Gate)

**工程铁律**: 基线先行绝不回归 · EventType 纯增量扩展 (ADR-0001) · 每次 CLI 行为必发 Event (含只读的 `.viewed` 事件) · 事件一律走 EventLogger · JSON 存储原子写、损坏报错不静默 · 新能力先测试后实现 (TDD) · 零写命令铁律 (Git 只读)。

---

*文档: docs/design/ (架构/CLI/事件模型/验证模型) · docs/adr/ (决策记录) · docs/vision.md · docs/roadmap.md · docs/lifecycle-model.md*
