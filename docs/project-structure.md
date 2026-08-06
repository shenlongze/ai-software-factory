# 项目结构 (project-structure)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 与 v1.0 Release 一致
> 关联文档: [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) · [core-boundary.md](./core-boundary.md) · [extension-model.md](./extension-model.md) · [system-architecture-review.md](./system-architecture-review.md)

本文档回答: **代码在哪里、每个模块的职责是什么、谁可以依赖谁、新能力怎么加**。

---

## 1. 仓库总览

```
ai-software-factory/
├── factory-core/          # 全部 Python 源码 (23 个模块子包, 顶层包)
│   ├── events/            # 事件日志 (唯一事实源, append-only SQLite)
│   ├── tasks/ workflows/ agents/ assignment/ execution/ runtime/
│   ├── recovery/ orchestration/ validation/ metrics/ dashboard/
│   ├── project/ workspace/ runtimes/ cli/
│   ├── understanding/ product/ providers/ git/ change/ changeflow/   # Extension 区
│   └── intelligence/                                                 # Intelligence 区
├── factory-console/       # Human Layer: 人类审核台
│   ├── service.py         # ConsoleService 七域只读聚合
│   ├── models.py events.py
│   ├── api/               # 8 个只读 GET 路由 (approvals/decisions/intelligence/lifecycle/projects/providers)
│   └── web/
│       ├── backend/fastapi_adapter.py   # FastAPI 适配器 (只读 GET)
│       └── frontend/                    # React + TypeScript (7 页面, 92 Vitest)
├── examples/markpad/      # Production Example: 真实项目 MarkPad (Flutter/Dart)
│   ├── project.yaml  agents.yaml  skills.yaml  workflows.yaml  README.md
├── docs/                  # 权威文档 + design/ 阶段报告 + adr/ (ADR-0001–0035)
├── tests/                 # 23 个域目录, 4090 pytest 用例
├── scripts/               # 一次性验证/审计脚本 (当前为空占位)
├── pyproject.toml         # 打包 + pytest 配置 (pythonpath=factory-core)
└── $SMOKE_ROOT/           # 验证环境工厂根 (factory.db + JSON stores + 事件)
```

> 顶层 `agents/ cli/ dashboard/ knowledge/ mcp/ runtimes/ skills/ src/ validation/ workflows/`
> 为空目录, 为 Phase 0 骨架占位; 实际实现在 `factory-core/` 对应子包。

---

## 2. factory-core — 分层模块图

**依赖单向向下, 禁止反向依赖与循环 import** (跨包引用一律函数内延迟 import):

```
┌────────────────────────────────────────────────────────────────────┐
│ Human Layer: factory-console/  (ConsoleService 七域只读聚合)        │
│   api/ (8 只读 GET 路由) + web/backend + web/frontend (React 7 页)  │
└───────────────────────────────┬────────────────────────────────────┘
                                │ 只读调用各域 Store/Service (零写 API)
┌───────────────────────────────▼────────────────────────────────────┐
│ Intelligence: intelligence/  (Decision / Recommend / Experience)    │
│   只复用 events + product (只读)                                    │
└───────────────────────────────┬────────────────────────────────────┘
                                │ 事件 + 只读复用
┌───────────────────────────────▼────────────────────────────────────┐
│ Extension: understanding/ product/ providers/ git/ change/          │
│            changeflow/   (只 import events + 区内依赖)               │
└───────────────────────────────┬────────────────────────────────────┘
                                │ 只 import events (Core)
┌───────────────────────────────▼────────────────────────────────────┐
│ Core (冻结原语): events/ tasks/ workflows/ agents/ assignment/      │
│   execution/ runtime/ recovery/ orchestration/ validation/ metrics/ │
│   dashboard/ project/ workspace/ runtimes/ cli/ — 零领域依赖         │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core — 冻结的通用原语 (零领域依赖)

Core 是工厂的骨架, 不关心任何领域 (软件/文档/市场分析都以同样方式运转)。
判定标准: **换一个领域/工具/模型, 这个能力还需要吗?** 需要 → Core; 否则 → Extension。

| 模块 | 职责 | 依赖 | 禁止依赖 | 扩展方式 |
|:-----|:-----|:-----|:---------|:---------|
| `events/` | Event Logger: `events` 表 append-only, `seq` 回放锚点, EventType 纯增量扩展 (ADR-0002) | 无 (stdlib + pydantic) | 任何领域包 | 新增 EventType 成员, 不加表不改表 |
| `tasks/` | 任务状态机 + JSON 持久化 | events | 领域包 | 新任务字段 |
| `workflows/` | 声明式工作流定义 + Engine (状态机/推进) | events | 领域包 | `workflow add` 或内置 definitions |
| `agents/` | AgentRegistry + SkillRegistry (find_by_skill), agent = 角色 + skill 集 + runtime 偏好 | events | 领域包 | `agent add` / `skill add` / SKILL.md |
| `assignment/` | AgentMatcher (role 精确 + skills 命中≥1, ADR-0008) + Allocator + 状态更新 | events | 领域包 | 无 (纯逻辑) |
| `execution/` | Dispatcher/Runner/Service: 执行调度与记录 | runtime + events | 领域包 | 无 |
| `runtime/` | **唯一执行出口**: `RuntimeAdapter` 抽象接口 + RuntimeRegistry (runtimes.json) + adapters/ (hermes/echo) | events | 具体 Runtime 实现 | 新 Adapter 文件 + 注册, Core 零改动 |
| `recovery/` | Checkpoint + EventReplay + RecoveryService: 断点续跑零丢失 | events | 领域包 | 无 |
| `orchestration/` | OrchestrationPipeline: 工作流→匹配→分配→执行→推进, 失败无半完成 | events | 领域包 | 无 |
| `validation/` | 三层验证引擎 L1 Factory / L2 Workflow / L3 Artifact (+ 可选 L4 Change 注入) | events | 领域包 | 新规则 (rules.py), L4 经延迟 import 破环 |
| `metrics/` | 六域指标: 只读聚合 (first_attempt_success / failure_reason_count ...) | events | 领域包 | 新 Calculator |
| `dashboard/` | 只读快照 + Rich 渲染: 20 视图, 无写入口 | events | 领域包 (见 §5 例外) | 新视图 (只读) |
| `project/` | ProjectDefinition 解析: project.yaml (name/language/repository/tech_stack/runtime_preferences) | events | 领域包 | 新 YAML 声明 |
| `workspace/` | 多项目工作区: workspace.yaml + 自动发现 + 跨项目事件过滤 | events | 领域包 | workspace init |
| `runtimes/` | 能力目录: catalog.json 能力描述 + 默认定义 (hermes/echo/mock 只读) + find_by_capability | events | 领域包 | catalog.json 声明 |
| `cli/` | 组合根: 23 顶级命令组 / 77 叶子命令; 每次命令发审计事件 | 全部模块 | 顶层 import 领域包 (只允许函数内延迟导入, 有测试断言) | 新命令组 (延迟导入) |

---

## 4. Extension — 领域能力 (声明式注册, 不修改 Core)

任何依赖具体工具/平台/模型/业务领域的能力一律走 Extension。
**铁律: 新增任何能力不修改 Core。**

| 模块 | 职责 | 依赖 | 扩展方式 |
|:-----|:-----|:-----|:---------|
| `git/` | Git 集成 (Phase 6C): 失败安全 Client + Service + Task 关联; `include_git` 缺省关 (Git 可选, 原则⑧) | events | 新 git 命令/只读接入 |
| `change/` | Change Intelligence (Phase 6D): commit 解析 / analyzer / 自动关联 / L4 Change Validation | events + git | 新规则 |
| `changeflow/` | Change Driven Workflow (Phase 6E): ChangeTrigger + 4 规则引擎 + 触发链 | events + change | 声明式触发器 (triggers register) |
| `understanding/` | Project Understanding (Phase 7): 10 阶段注册表 + 7 Artifact 注册化 + 规则分析 + 结构化建议 | events | 新阶段/新 Artifact 类型 |
| `product/` | Product Intelligence (Phase 9): Artifact/Lineage/Confidence + ProductIdea + ApprovalGate + Lifecycle 编排 + Generation + Experience | events | 新产物类型/生成器 |
| `providers/` | LLM Provider 抽象 (Phase 8): ProviderDefinition + 统一 I/O + Adapter + Registry + Capability/Cost/Usage/Feedback + CostAwareSelector | events | 新 Provider 声明 (catalog.json) + Adapter |

**区内依赖 (单向)**: `change → git`, `changeflow → change`。Extension 一律不反向依赖 Core 之外的任何模块。

---

## 5. Intelligence — 决策智能

| 模块 | 职责 | 依赖 |
|:-----|:-----|:-----|
| `intelligence/` | DecisionIntelligence (决策链 + Evidence 强制 + Risk R1–R5) · RecommendationEngine (四因素评分 0.35/0.30/0.20/0.15 + Reasoning 解释) · ExperienceAnalyzer (半衰期衰减/正负聚合) · TaskEvaluator · 三 Store 独立空间原子写 | events + product (只读复用) |

Intelligence 只消费事件与 Product 产物, 不反向影响 Extension/Core 的行为。

---

## 6. Human Layer — factory-console

| 部分 | 职责 |
|:-----|:-----|
| `service.py` | ConsoleService 七域只读聚合: projects / approvals / agents / decisions / cost / experience / activity; 失败安全 (空工厂 → 全空域) |
| `api/` | 8 个只读 GET 路由: `/api/dashboard` `/api/projects` `/api/projects/{id}/lifecycle` `/api/approvals` `/api/decisions/{id}` `/api/recommendations` `/api/experience` `/api/providers` |
| `web/backend/fastapi_adapter.py` | FastAPI 适配器 (只 GET, 零写路由) |
| `web/frontend/` | React + TypeScript: 7 页面 (Dashboard/Projects/Lifecycle/Approval/Decisions/Providers/Intelligence) + Simple/Expert 切换 + 只读 api client; 92 Vitest |
| `models.py` `events.py` | 响应模型 + 3 个审计事件 (console.viewed / console.dashboard.viewed / console.approval.opened) |

**权限边界**: Console 只读聚合, 零写 API, 不自动执行、不自动批准; 删除 factory-console → Factory 照常运行 (有测试断言)。

---

## 7. examples / docs / tests / scripts

| 目录 | 内容 |
|:-----|:-----|
| `examples/markpad/` | Production Example (ADR-0013): `project.yaml` 项目定义 + `agents.yaml` 角色映射 + `skills.yaml` 技能目录 + `workflows.yaml` 工作流映射 (含 required_role/required_skill)。**只读声明**: 展示用 `project list/show`, 实际注册走 CLI (`agent add` / `skill add` / `workflow add`) |
| `docs/` | 权威文档 30+ 篇 (vision / design-principles / lifecycle-model / capability-architecture / core-boundary / extension-model / 各 Phase 模型文档) + `design/` 阶段设计与状态报告 + `adr/` ADR-0001–0035 |
| `tests/` | 24 个域目录, 与各模块一一对应 (含 `tests/console/`); 共 **4090 pytest** 用例 |
| `scripts/` | 一次性验证/审计脚本占位 (如 real-world-validation 脚本) |

---

## 8. 依赖方向验证结论 (2026-08-06 复核)

| 检查项 | 结果 |
|:-------|:-----|
| 冻结原语层 (events/tasks/workflows/execution/runtime/recovery/assignment/orchestration/validation/metrics/project/workspace/runtimes/agents) 引用领域模块 (understanding/product/providers/git/change/changeflow/intelligence) | ✅ **0 处** |
| Extension (understanding/product/providers/git/change/changeflow) 反向依赖 Core 业务逻辑 | ✅ 仅 import `events` (Core) + 区内依赖 (change→git, changeflow→change) |
| Intelligence 反向依赖 Extension | ✅ 仅 `events` + `product` 只读复用 |
| Console 写入口 | ✅ 零写 API, 仅 8 个 GET 路由, 只读聚合 |
| 循环 import | ✅ 无环 |

**两个已知只读例外 (冻结审计已确认, 均不构成业务依赖)**:

1. `dashboard/models.py` 顶层 `from git.models import GitChange/GitCommit/GitContext` — 仅用于 git/change/changeflow 三个可选视图的渲染类型, `include_git` 缺省关。
2. `dashboard/collector.py` 与 `cli/commands.py` 对领域包一律**函数内延迟导入** (标注"零 Core 依赖"), CLI 是组合根, 有测试断言约束 (`test_product_removal.py` 等)。

> 结论: 三区 + Human Layer 单向依赖成立; Core 冻结有效, 无需重构。
