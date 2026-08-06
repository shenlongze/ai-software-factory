# AI Software Factory

> **AI 时代的软件生产操作系统** — 管理 AI 员工 (Agent)、组织软件生产流程 (Workflow)、连接各种 Agent Runtime 的工厂控制平面。
> 不是聊天机器人, 不是单个 Agent, 不是代码生成工具。

## Vision

让软件生产从"靠人盯着 AI 干活"升级为**可管理、可观察、可验证、可积累、可扩展、可复制**的工厂化运转:

- **可管理** — 管理 AI 员工 (Agent) 的生命周期、职责与可靠性
- **可观察** — 任何时刻都知道每个 Agent 在做什么、进度、阻塞 (Event 流 = 唯一事实源)
- **可验证** — Agent 自报告 ≠ 完成, Validation 结果才是事实
- **可积累** — 架构决策 / 缺陷 / 经验沉淀为企业资产
- **可扩展** — 不绑定任何 Agent 框架, Runtime 可插拔 (Hermes / Claude Code / LangGraph / OpenHands...)
- **可复制** — 一套平台支持多项目并行生产

**成功标准**: 一个任务从创建到交付全程可观察、可恢复、可验证; 多项目并行生产、知识跨项目复用; 新 Runtime / 角色 / Skill 声明式接入 (零代码); 指标达标 (first_attempt_success > 95%, path_errors = 0, human_intervention 最小化)。

## Current Capability

已完成 12 项核心能力 (全部经 pytest 验证):

| # | 能力 | 说明 |
|:-:|:-----|:-----|
| 1 | **Workspace** | 多项目工作区 — workspace.yaml 管理、managed/示例项目自动发现、项目级数据隔离 |
| 2 | **Task Management** | 任务状态机 + JSON 持久化 + 事件时间线 + 项目归属 |
| 3 | **Workflow Engine** | 声明式多步工作流 + 状态机 + 内置定义 (feature-delivery / desktop-feature / bug-fix / release) |
| 4 | **Agent System** | Agent / Skill 注册表 + 角色/技能匹配 (Matcher) + 分配生命周期 (Allocator) + 状态追踪 |
| 5 | **Runtime Adapter** | 统一 Runtime 抽象 + 执行分派/运行 (Dispatcher / Runner / Service) + 内置 echo / hermes 适配器 |
| 6 | **Hermes Integration** | HermesRuntimeAdapter 子进程接入 (FACTORY_HERMES_CMD / FACTORY_HERMES_TIMEOUT 可配置) |
| 7 | **Validation Engine (L1–L4)** | 四层验证: L1 基础 / L2 结构 / L3 行为 / L4 Change 语义, 规则可插拔 |
| 8 | **Recovery** | Checkpoint 快照 + EventReplay 断点恢复 (四场景: 运行中工作流/执行/Agent/已完成) |
| 9 | **Dashboard (16 视图)** | Rich 只读仪表盘: 总览/任务/Agent/工作流/执行/恢复/指标/目录/项目/工作区/Git/Change/Change Flow... |
| 10 | **Metrics** | 六域指标: 任务/执行/Agent/工作流/验证/失败 (first_attempt_success_rate 等) |
| 11 | **Git Intelligence** | Git 只读 + 审计: status/diff/commits + task↔commit 自动关联 |
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

- **入口**: `factory` CLI (argparse), 18 组命令, 每次调用必发审计 Event
- **组合根**: 编排/恢复/变更触发等跨域流程只做装配, 不复制领域逻辑
- **域模块**: 每个包只干一件事 (KISS), 读写分离 — 观察域与集成域只读不写状态
- **存储**: 事件走 SQLite (append-only, 可回放重建状态); 状态走 JSON (原子写, 损坏即报错不静默)

## Current Status

- **20 个 Phase 全部交付** (Phase 0 设计稿 → Phase 1 观察层 → ... → Phase 6E Change Driven Workflow)
- **2159 tests 全绿, 零核心破坏** — EventType 纯增量扩展 (ADR-0001), 每阶段基线只增不减
- **20 份 ADR 决策记录** (docs/adr/0001–0020), 设计文档齐全 (docs/design/, docs/vision.md, docs/roadmap.md)
- 技术栈: **Python 3.12+ / Pydantic v2 / SQLite (事件) / JSON (状态) / Rich (Dashboard) / argparse (CLI) / PyYAML (示例配置)** — 单进程, 零数据库 ORM

## Future Roadmap

| 方向 | 目标 |
|:-----|:-----|
| **Project Understanding** | 项目理解 — 从静态示例配置升级为运行时理解项目结构/依赖/领域语义, 为任务拆解与验证提供上下文 |
| **LLM Provider** | LLM 判定接入 — 验证与变更分析从纯规则判定升级为 LLM 辅助语义判定, Provider 可插拔 |
| **Product Intelligence** | 产品智能 — 从事件流沉淀产品级洞察: 缺陷模式、效率瓶颈、跨项目知识复用 |
| **Operations** | 运营闭环 — 多项目排期、资源分配、告警与日常运营, 让 Factory 成为日常运转的系统 |

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

常用命令: `factory status` (工厂总览) · `factory event logs` (事件时间线) · `factory validate T-001` (L1–L4 验证) · `factory dashboard --view all` (16 视图仪表盘) · `factory metrics` (六域指标) · `factory git status` / `factory change analyze T-001` (变更智能)。全部命令支持 `--json`。

## Design Philosophy

七大设计原则, 全部来自 MarkPad 实战的实证教训 (docs/design/architecture.md §0):

1. **KISS — 最小模块集** — 每个模块只干一件事
2. **Orchestrator 不写代码** — 管理层只决策、委派、验收
3. **一切以事件为中心** — 任何状态变化都落事件流, 事件 = 唯一事实源
4. **自报告不可信, 验证独立** — Agent 说的不算, 验证引擎说了算
5. **文件即事实** — 文件范围声明 + 锁 + 校验, 杜绝越权写
6. **可断点续传** — 任何时刻可中断、可恢复
7. **人只出现在少数闸口** — 产品冲突 / 架构变更 / Scope 扩展才暂停

**工程铁律**: 基线先行绝不回归 · EventType 纯增量扩展 (ADR-0001) · 每次 CLI 行为必发 Event (含只读的 `.viewed` 事件) · 事件一律走 EventLogger · JSON 存储原子写、损坏报错不静默 · 新能力先测试后实现 (TDD)。

---

*文档: docs/design/ (架构/CLI/事件模型/验证模型) · docs/adr/ (决策记录) · docs/vision.md · docs/roadmap.md*
