# 扩展模型 (extension-model)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: 冻结报告配套文档 (Extension 体系完整)
> 关联文档: [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) · [core-boundary.md](./core-boundary.md) · [design-principles.md](./design-principles.md) · [skill-model.md](./skill-model.md) · [agent-model.md](./agent-model.md)

Core 是冻结的 8 项通用原语 (core-boundary.md); **一切新能力都从这里进入系统**。
本文档定义四类扩展、声明式注册机制、当前实现 vs 未来差距、以及新增能力的标准流程。

---

## 1. 四类扩展 — 全景

```
Agent (角色配置实例)
  ├── Skills     能力声明   (flutter-development / market-analysis / excel-report / seo)
  ├── MCP Tools  外部工具   (GitHub / Jira / Figma / AWS / Google Drive)
  └── Runtime    执行方式   (Hermes CLI / Codex CLI / Claude API / Local Model)
        └── Provider      LLM 来源 (OpenAI API / Anthropic / Local)
```

| 扩展类型 | 回答的问题 | 本质 | 接入载体 |
|:---------|:-----------|:-----|:---------|
| **Skill** | 会做什么 (能力) | 程序性知识: "某类任务怎么做、有哪些坑、怎么验证" | `SKILL.md` (五段式) + `meta.json` 能力声明 |
| **MCP** | 能连什么 (外部工具) | 外部系统的标准协议桥接 | MCP server 声明 (JSON): server 名 + 工具清单 |
| **Runtime** | 谁去干活 (执行方式) | 执行器: 启动外部进程 / 调用 Agent 框架 | `RuntimeAdapter` 接口实现 + 注册信息 |
| **Provider** | 用什么脑子 (LLM 来源) | 智能层: 具体模型/API 来源 | Provider 接口实现 (Phase 8) + 注册信息 |

**关系要点** (冻结报告 §2 确认):

- Skill 独立于 Agent: SkillRegistry 已有; Agent = 角色 + skill 集 + MCP 工具集 + runtime 偏好。
- Runtime = 执行器; Provider = LLM 来源; **一个 Runtime 可对接多个 Provider** (如
  Hermes Runtime 下接 OpenAI / Claude / Local 均可, 由 per-role 偏好路由)。
- 四类扩展都挂在 Agent 配置上装配, 但注册机制是统一的: **声明式 JSON, 零 Core 代码改动**。

---

## 2. 声明式注册机制

**铁律: 新增任何能力不修改 Core。** 所有扩展以声明式数据注册:

| 新增对象 | 声明物 | 注册目标 | Core 改动 |
|:---------|:-------|:---------|:----------|
| 新 Skill | SKILL.md + meta.json | SkillRegistry | 无 |
| 新 Agent/角色 | role JSON (scope/outputs/forbidden) | AgentRegistry | 无 |
| 新工作流 | workflow JSON (定义/状态转换) | WorkflowStore | 无 |
| 新 MCP server | MCP server JSON (工具清单) | MCP 注册表 (规划) | 无 |
| 新 Runtime | catalog.json 能力描述 + runtimes.json 实例 | RuntimeCatalog + RuntimeRegistry | 无 |
| 新 Provider | Provider 声明 (Phase 8) | ProviderRegistry (规划) | 无 |

> 实例: OpenClaw skill / Codex plugin / MCP server / 第三方 Agent —— 全部是
> 新增一份声明, 不需要碰 tasks/workflows/events/execution 任何一行核心代码。

**三层分离原则** (ADR-0014, Phase 5A1): 目录不派发、注册不执行。

```
runtimes/ Catalog   = 能力描述 (catalog.json)      — 有什么能力
runtime/  Registry  = 实例可用状态 (runtimes.json) — 哪些可用/禁用
Adapter             = 执行器                        — 怎么执行
```

目录、注册表、执行器三者解耦: 有目录不一定已注册, 已注册不一定在执行。

---

## 3. 当前实现 vs 未来

| 扩展能力 | 状态 | 实现位置 / 现状 | 差距 |
|:---------|:----:|:----------------|:-----|
| **AgentRegistry** | ✅ | `factory-core/agents/registry.py`: `register/get/list/remove/find_by_skill` | 已完备 (Phase 3B); Agent = 角色 + skill 集 + runtime 偏好 |
| **SkillRegistry** | ✅ | 同文件 (agents/registry.py): Skill 独立于 Agent 注册; 内置集 flutter/frontend/backend/testing/validation | 自定义 Skill = 新增 SKILL.md + 登记, 已可用; `skills/` 目录为外部装载占位 |
| **RuntimeAdapter** | ✅ | `factory-core/runtime/adapter.py`: 抽象接口 `execute(request) -> ExecutionResult`; **实现已落地** `runtime/adapters/`: `hermes.py` (HermesRuntimeAdapter, 默认实跑) + `echo.py` (EchoRuntimeAdapter, 测试/冒烟) + mock 供测试 (tests/runtime) | 接口冻结 + 首批适配器可用; 新增 Runtime = 新 Adapter 文件 + 声明注册 |
| **Runtime Catalog** | ✅ | `factory-core/runtimes/` (catalog.json 能力描述, 可插拔目录); CLI `factory runtime add/list/test` + `runtime catalog list/show` | 已完备 (Phase 5A1/5A2) |
| **MCP** | 🚧 | `mcp/` 目录占位; 接入方式已定 (JSON 声明工具清单) | 注册表/协议桥未实现; 规划经 RuntimeAdapter / Validation 封装执行, 不裸调 |
| **Provider** | 🚧 | Phase 8 LLM Provider Abstraction (roadmap §3): `factory-core/providers/` (interface/registry/store/adapters) + CLI `factory provider list\|add\|test\|use` + 事件 `provider.registered` / `provider.usage.*` | **当前最大差距** (评审确认): 智能层目前经 Hermes 绑定; 执行链路已就绪 —— Assignment/Execution 已按 `runtime_id` 解析, Phase 6A 已建 `runtime_preferences` 字段, 只差 Provider 层实现 |

### 3.1 已就绪的"半场" — per-role 偏好路由

`runtime_preferences` (project.yaml, Phase 6A 已建) 声明角色 → (provider, runtime) 偏好,
是 Provider 层落地后的路由依据:

```yaml
runtime_preferences:
  architect:  { provider: claude }   # 架构决策 → Claude
  developer:  { provider: codex }    # 编码 → Codex
  tester:     { provider: hermes }   # 验证/测试 → Hermes
```

换工具 = 改配置, 不是改流程 (原则③)。同一工作流可在不同 Provider 间切换, Core 零改动。

---

## 4. 扩展流程 — 新增能力的标准步骤

四类扩展统一走 **声明 → 注册 → 复用 Core 原语** 三步。区别只在声明物与注册目标。

### 4.1 新增 Skill (能力声明)

1. **起草**: 按 skill-model 五段式写 `SKILL.md` (frontmatter: name/category/description/
   trigger; 步骤含出口条件; pitfalls 实证模板; 独立可执行的验证段)。
2. **登记**: 写入 SkillRegistry (meta.json 能力声明: capabilities/version), 同步索引。
3. **绑定**: 挂到 Agent/角色上 (role JSON 的 `skill` 字段); 无命中即不可被委派加载。
4. **试用沉淀**: 首个任务结束后回写 pitfalls; 使用中发现的坑当场 patch (skill-model §4)。

### 4.2 新增 MCP 工具 (外部工具)

1. **声明**: 写 MCP server JSON (server 名 + 工具清单 + 端点/认证)。
2. **注册**: 登记到 MCP 注册表 (规划实现); 工具清单对 Agent 可见、可匹配。
3. **接入执行**: MCP 工具经 RuntimeAdapter / Validation 封装执行, **不裸调**;
   每次调用发审计事件 (复用 Core Event Logger)。
4. **装配**: Agent 配置声明可用工具集; 权限/范围按工具粒度声明。

### 4.3 新增 Runtime (执行方式)

1. **实现**: 继承 `RuntimeAdapter` 接口, 实现 `execute(request) -> ExecutionResult`
   (启动外部进程 / 调用 Agent 框架的细节全在 Adapter 内部)。
2. **声明**: 写 catalog.json 能力描述 (能做什么) → 登记 RuntimeCatalog。
3. **注册**: 写 runtimes.json 实例状态 (AVAILABLE/DISABLED) → RuntimeRegistry;
   `factory runtime add/list/test` 验证连通。
4. **复用**: AgentAllocator 按偏好与可用性选执行器; 同一任务换 Runtime 零 Core 改动
   (ADR-0006 测试约束: 同一任务 ≥2 种 Runtime 跑通)。

### 4.4 新增 Provider (LLM 来源, Phase 8)

1. **实现**: 实现 Provider 接口 (interface.py) → `providers/adapters/` 各实现
   (hermes-provider / codex-provider / openai-provider / local-provider)。
2. **注册**: `factory provider add` → ProviderRegistry; 状态/测试走 store 复用
   Phase 4B-1 三段式模式 (interface/registry/store)。
3. **路由**: 在 project.yaml 的 `runtime_preferences` 声明 per-role 偏好;
   Assignment/Execution 按 `runtime_id` 解析 (链路已就绪, 零执行层改动)。
4. **复用**: 同一工作流跨 Provider 执行, 只读审计可查 (`provider.usage.*` 事件带
   provider_id); 未选 Provider 时默认 hermes, 向后兼容。

---

## 5. 扩展遵守的 Core 契约

任何扩展接入时不可破坏以下 Core 契约:

1. **事件契约**: 一切行为产生 Event; 扩展只生产/消费事件, 不篡改历史 (原则①)。
   新领域事件按 domain 扩展 EventType 枚举 (ADR-0002 路径: 加成员不改表), 如
   `research.*` `prd.*` `ui.*` `deployment.*` `incident.*` `approval.*`。
2. **执行出口**: 任何"启动 Agent / 跑命令 / 调工具"只能走 RuntimeAdapter 协议
   (或 Validation/MCP 封装), 不裸调 subprocess (原则③)。
3. **三层分离**: 扩展不得把"思考/决策/执行"混层 —— Provider 不决策,
   Runtime 不做决策, 决策归 Orchestration + 人工 (原则⑤)。
4. **失败安全**: 扩展层异常永不级联到 Core (evaluate 永不抛 / 触发失败转 ERROR /
   异常 → 规则 SKIP, 绝不误报 FAIL) (原则⑦)。
5. **可回退**: 扩展能力可整体停用 (`include_git` / `include_change` 缺省关的
   模式), 停用后系统行为退回上一阶段且无残留异常。

---

## 6. 现状 vs 未来 — 一张表

| 维度 | 现在 (冻结日) | 未来 (Phase 7–11 后) |
|:-----|:--------------|:----------------------|
| 能力 | SkillRegistry ✅ 内置 5 技能, 可自定义 | 任意领域 Skill (市场/UI/SEO/Office) 声明即用 |
| 外部工具 | MCP 🚧 目录占位 | GitHub/Jira/Figma/AWS/Database 全部 MCP 声明接入 |
| 执行 | RuntimeAdapter ✅ (echo/hermes/mock) | 任意 Agent 框架/CLI 即插即拔 |
| 智能 | Provider 🚧 (Hermes 绑定, Phase 8 最大差距) | OpenAI/Claude/Codex/Local 多 Provider, per-role 偏好路由 |
| 组织 | Workspace/Project ✅ | 任意阶段接入 (Idea → 生产, 原则⑨) |
| 审核 | CLI 决策门 ✅ | Web 审核台 (Phase 11, 只设计不实现) |

**冻结结论**: 扩展体系完整, 无需重构。冻结后新能力一律走本文档 §4 流程
(声明 → 注册 → 复用 Core 原语), 不修改 Core 行为。

---

## 7. 一句话总结

> **四类扩展 (Skill 能力 / MCP 工具 / Runtime 执行 / Provider 智能) 全部声明式
> JSON 注册, 零 Core 代码改动; AgentRegistry ✅ / SkillRegistry ✅ / RuntimeAdapter ✅
> 已落地, MCP 🚧 / Provider 🚧 (Phase 8) 是唯二剩余差距。**

上一份文档: [core-boundary.md](./core-boundary.md)(Core 是什么、什么不能进)。
