# Core 边界 (core-boundary)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 冻结报告配套文档 (架构冻结有效, 无需重构)
> 关联文档: [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) · [design-principles.md](./design-principles.md) · [architecture.md](./architecture.md) · [extension-model.md](./extension-model.md)

本文档回答三个问题:

1. **什么必须留在 Factory Core**(通用原语, 冻结后不修改行为)?
2. **什么永远不能进 Core**(领域能力, 一律走 Extension)?
3. **新增能力时怎么判断**(先问: 是通用原语还是领域能力?)

---

## 1. Factory Core 定义 — 必须保持的 8 项通用原语

Core 是"工厂的骨架": 状态、流程、事件、验证、抽象。它不关心**任何领域** —
不管工厂生产的是软件、文档还是市场分析, 这 8 项原语都以同样方式运转。

| # | 能力 | 模块 (factory-core/) | 关键 API / 载体 | 为什么在 Core |
|:-:|:-----|:---------------------|:----------------|:--------------|
| 1 | **状态管理** | `tasks/` `workflows/` `agents/` `assignment/` `execution/` | Task/Workflow/Agent/Assignment/Execution 状态机; 定义性数据落表, **status 一律由事件投影** | 一切工作的最小事实单元。任何领域任务最终都归结为"某状态对象在某时刻处于某状态"; 状态机与投影规则与领域无关 |
| 2 | **生命周期** | `workflows/` `recovery/` | WorkflowEngine (engine.py) + 状态转换 + 恢复; workflow 定义 = JSON 声明式 | "把一个工作从开始推到完成"是通用骨架; 流程推进 + 断点续跑是所有领域能力复用的载体 |
| 3 | **调度** | `orchestration/` `assignment/` | OrchestrationPipeline (匹配→分配→执行) + AssignmentMatcher (Agent 匹配, 按 role/skill/runtime 偏好) | 决定"谁做什么"是纯逻辑, 不依赖具体工具或模型; 换任何执行器, 调度逻辑不变 |
| 4 | **执行抽象** | `runtime/` | **RuntimeAdapter 接口** (adapter.py: `execute(request) -> ExecutionResult`, **不实现任何具体 Runtime**); RuntimeRegistry (runtimes.json 实例状态) | 唯一执行出口 (架构三条硬规则之一)。Core 不裸调 subprocess / LLM / Agent 框架; 换 Runtime = 换 Adapter, Core 零改动 |
| 5 | **事件审计** | `events/` | Event Logger: `events` 表 (SQLite) append-only, `seq` 自增回放锚点, 只 INSERT 永不 UPDATE/DELETE; EventType 枚举扩展走 ADR-0002 路径 (加成员不改表) | **Event 是唯一事实源** (原则①): 状态是事件的投影, 指标是事件的聚合, 审计是事件的回放。Core 一旦失去事件权威性, 一切恢复/观测/信任崩塌 |
| 6 | **恢复** | `recovery/` | checkpoint.py (检查点落盘) + replay.py (事件回放) + service.py (恢复编排); 协议: 断点续跑只认落盘状态 + 产物 | 截断/失败零丢失是工厂可信度的底线 (原则⑥); 恢复不依赖任何对话记忆, 与领域无关 |
| 7 | **观测基础** | `dashboard/` `metrics/` | Dashboard 16 视图 + Metrics 全部**基于 Event 的只读聚合** (first_attempt_success / path_errors / human_intervention), 无写入口 | 可观测是可管理的前提 (原则②), 但观测只做**聚合展示**, 不做领域判断 —— 领域判断属于 Extension |
| 8 | **组织** | `workspace/` `project/` | Workspace/Project 分层: workspace.yaml + project.yaml 挂载真实状态 (接入 = 挂载, 原则⑨); 跨项目事件过滤 | "工厂管多个项目"是平台层事实; 分层与挂载机制与具体项目内容无关 |

**Core 的完整清单即上表 8 项**。已实现的独立模块中, `git/` `change/` `changeflow/`
是 Core 之外的可选能力模块 (见 §2), `validation/` 属"验证"原语范畴, 归 Core。

---

## 2. 不能进 Core 的清单 — 全部 Extension

任何**领域能力** (依赖具体工具、具体平台、具体模型、具体业务领域) 不得进入 Core。
Core 零领域依赖是硬边界, 不是软偏好。

| 领域 | 类型 | 接入方式 | 现状 |
|:-----|:-----|:---------|:-----|
| Git / GitHub | Integration | Skill / MCP | `git/` 独立模块 (Phase 6C): 只读接入 + 审计事件; `include_git` 默认关 (原则⑧); 未来可注册 github MCP |
| Jira / Figma / AWS / Database | 外部工具 | **MCP** | 🚧 mcp/ 目录占位, 声明式 JSON 注册 (规划) |
| Market Research / UI Generation / Office / SEO | 能力 | **Skill** | SkillRegistry ✅ (内置集: flutter/frontend/backend/testing/validation), 自定义 SKILL.md + meta.json |
| Monitoring / Incident | 运营 | Operations Layer | 🚧 Phase 10 (依赖 Phase 7/8); 经事件聚合 + 告警, 复用 Core Event Logger |
| 具体 LLM (OpenAI / Claude / Local) | 模型来源 | **Provider** | 🚧 Phase 8: `factory-core/providers/` (interface/registry/store/adapters) + `factory provider list\|add\|test\|use` |

### 2.1 判定规则: 为什么这些不能进 Core

- **Git/GitHub**: 平台的心脏是事件流与状态机, 不是 Git (原则⑧)。Git 只是项目上下文
  的一种来源; Core 零 Git 依赖 —— task/workflow/execution/event 核心路径不 import git。
  缺 Git 上下文 → L4 判定 SKIP (不是 FAIL)。
- **Jira/Figma/AWS/Database**: 外部系统, 协议与生命周期都归厂商/社区维护。Core 一旦
  直连外部系统, 外部变更即 Core 变更 —— 违背"增量演进, 零核心破坏" (原则⑦)。
- **Market Research / UI Generation / Office / SEO**: 领域操作方法, 本质是"某类任务
  怎么做"的知识, 即 Skill 的定义域 (skill-model §1)。知识可以沉淀、可以过期、可以修补,
  不该冻结在 Core 里。
- **Monitoring/Incident**: 运营动作。告警/事件处置复用 Core 事件流但判断逻辑 (什么算
  事故、如何升级) 是领域策略, 属 Operations Layer (Phase 10)。
- **具体 LLM**: 模型会变、框架会换, 工厂的组织能力不变 (原则③)。LLM 是执行器的一部分,
  经 Provider 接入, 不硬绑定任何一家。

---

## 3. 边界原则 (三条铁律)

1. **Core = 通用原语**: 状态 / 流程 / 事件 / 验证 / 抽象。凡是"任何项目、任何领域、
   任何工具都同样需要"的能力, 才是 Core。
2. **Extension = 领域能力**: 凡依赖具体工具 (Jira/Figma/AWS)、具体平台 (GitHub)、
   具体模型 (OpenAI/Claude/Local)、具体业务领域 (市场/UI/SEO/Office) 的能力,
   一律经 Skill / MCP / Runtime / Provider **声明式注册**接入 (详见 extension-model.md)。
3. **Core 零领域依赖**: Core 的 import 图里不得出现任何领域工具、具体 LLM、外部系统。
   违反即视为边界破坏, 必须回滚或重构为 Extension。

辅助判据 (来自 design-principles.md, 全部与边界互证):

- 原则① Event is source of truth → Core 拥有事件权威, Extension 只生产/消费事件
- 原则③ AI must be replaceable → 任何"谁去干活 / 用什么脑子"都是可替换的 → Runtime/Provider
- 原则⑦ Incremental evolution → 新能力复用既有核心, 不修改核心 → 声明式扩展
- 原则⑧ Git is optional → 连 Git 都只是可选能力, 何况更具体的工具

---

## 4. 冻结规则 — 新能力判断流程

架构已冻结。**冻结后: 不修改 Core 行为; 新能力一律走 Extension 注册。**
任何新能力建议, 按以下流程判定 (第一步即一票否决):

```
新能力需求
  │
  ├─ Q1: 它是通用原语还是领域能力?
  │        (问: 换一个领域/工具/模型, 这个能力还需要吗?)
  │        领域能力 ───────────────────────→ 走 Extension (§2 接入方式) ✅
  │        通用原语 ──→ 继续
  │
  ├─ Q2: 它是否已被 Core 8 项覆盖?
  │        (状态 / 生命周期 / 调度 / 执行抽象 / 事件审计 / 恢复 / 观测 / 组织)
  │        已覆盖 ──→ 复用现有原语, 不做新 Core 能力 ✅
  │        未覆盖 ──→ 继续
  │
  ├─ Q3: 它的实现是否触碰 Core 行为 (状态机/事件/恢复/适配器协议)?
  │        触碰 ──→ 冻结中, 拒绝。除非走"解冻评审" (见下) ⛔
  │        不触碰 ──→ 以独立模块 + CLI + Dashboard 视图 + 复用 Core API 方式
  │                   接入 (changeflow 模式, ADR-0020) ✅
  │
  └─ 解冻评审 (唯一例外路径, 极少触发):
       1. 边界评审: 证明该能力满足"通用原语 + 零领域依赖"两条铁律
       2. ADR 记录: 一个 Phase 一个 ADR, 记录收尾失败测试的契约裁定 (原则⑦)
       3. 测试只增不减: 存量 2159 测试全绿, 新增测试覆盖新原语
       4. 冻结确认: 评审通过后才可进入 Core; 默认拒绝
```

### 4.1 判断要点速查

| 问自己 | 答案若为"是" | 结论 |
|:-------|:-------------|:-----|
| 换掉具体工具/平台/模型后, 这能力还用得上吗? | 否 | Extension |
| 这是"某类任务怎么做"的知识吗? | 是 | Skill |
| 这是要连一个外部系统吗? | 是 | MCP |
| 这是"谁去干活/怎么执行"吗? | 是 | Runtime |
| 这是"用什么模型/脑子"吗? | 是 | Provider |
| 这是状态/流程/事件/验证/抽象本身吗? | 是 | 可能进 Core, 走 Q2/Q3 |

### 4.2 边界守护 (落地机制)

- **代码层面**: Core 模块 (tasks/workflows/events/execution/orchestration/recovery/
  runtime/runtime-adapter 等) 不 import `git/` `change/` 以外的领域依赖; CI 检查
  Core import 图, 出现领域包即失败。
- **测试层面**: 测试只增不减 (2159 → 单调增长); 每个 Phase 收尾有失败测试契约裁定。
- **文档层面**: 本文档 §1 清单是唯一权威 Core 清单; 任何变更先改本文档 + ADR, 再动代码。

---

## 5. 一句话总结

> **Core 是 8 项通用原语的冻结集合; 领域能力一律声明式注册为 Extension;
> 新能力先问"是通用原语还是领域能力"—— 领域能力走 Extension, 通用原语走解冻评审 (默认拒绝)。**

下一份文档: [extension-model.md](./extension-model.md)(四类扩展如何声明式注册接入)。
