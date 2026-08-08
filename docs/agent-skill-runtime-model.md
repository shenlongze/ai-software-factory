# Agent / Skill / Runtime / Provider 模型 (agent-skill-runtime-model)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 通用 AI Software Factory 的**统一扩展模型**:一个 Agent 如何由 角色 + 能力 + 执行方式 + LLM 来源
> 组装而成,以及新增能力时如何做到 **Core 零改动**。本模型是架构冻结报告的扩展模型
> (冻结 §二)与架构评审统一抽象(评审 §2)的落地细化,与当前代码实现一一对应。
> 关联文档: [agent-model.md](./agent-model.md)(角色/委派) · [skill-model.md](./skill-model.md)(能力声明)
> · [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) · [roadmap.md](./roadmap.md)(Phase 8)

---

## 1. 核心概念

**Agent(角色配置实例)** 是工厂中承担一项专业工作的执行主体。一个 Agent 由四类要素组装:

```
Agent (角色配置实例)
  ├── Skills     能力声明   (flutter-development / market-analysis / excel-report / seo)
  ├── MCP Tools  外部工具   (GitHub / Jira / Figma / AWS / Google Drive)
  └── Runtime    执行方式   (Hermes CLI / Codex CLI / Claude API / Local Model)
        └── Provider      LLM 来源 (OpenAI API / Anthropic / Local)
```

| 要素 | 一句话定义 | 回答的问题 | 现状 (代码) |
|:-----|:-----------|:-----------|:------------|
| **Agent** | 角色配置实例 = 角色 + skill 集 + MCP 工具集 + runtime 偏好 | "谁来做、带什么能力、用哪个执行器" | ✅ `AgentRegistry` (`agents/registry.py`), `Agent` 模型含 `role` / `skills` / `status` |
| **Skill** | 能力声明,独立于 Agent 的知识单元 | "这类任务怎么做、有什么坑" | ✅ `SkillRegistry`, `Skill` 模型 (`id/name/category/description/capabilities/version`) |
| **MCP Tools** | 外部工具接入层 | "能调用哪些外部系统" | ❌ 未实现 (`mcp/` 目录空, 评审 §2 差距表) |
| **Runtime** | 执行方式 = 执行器 | "用哪个框架/CLI 实际执行" | ✅ `RuntimeAdapter` 抽象 + `EchoRuntimeAdapter`/`HermesRuntimeAdapter` |
| **Provider** | LLM 来源 | "背后是哪个大模型服务" | ❌ 未抽象 (Phase 8 核心, 当前硬绑定 Hermes) |

> **关系口诀**: Agent 决定"做什么"(角色边界),Skill 决定"怎么做"(操作知识),
> MCP 决定"用什么外部工具",Runtime 决定"在哪执行",Provider 决定"用哪个大脑"。

---

## 2. 四要素详解

### 2.1 Agent = 角色配置实例

`agents/models.py` 的 `Agent` 模型 (Phase 3B) 已承载角色身份与 skill 引用:

```python
class Agent(BaseModel):
    id: str
    name: str
    role: str                      # 角色标识 (agent-model §2 注册表)
    description: str = ""
    skills: list[str]              # Skill.id 引用列表 (去重保序)
    status: AgentStatus            # AVAILABLE / WORKING / OFFLINE
    current_task: str | None       # 当前任务 id (引用, 不自动分配)
```

- `skills` 是 **Skill.id 引用列表**,不内嵌技能内容 — Skill 独立注册、Agent 按需装载,
  同一 Skill 可被多个 Agent 引用 (skill-model §1 解耦原则)。
- **现状差距**: MCP 工具集与 runtime 偏好目前**不在 Agent 模型上**,而是:
  - runtime 偏好已建在 **ProjectDefinition.runtime_preferences** (Phase 6A, `project/models.py`
    与 `workspace/models.py`, 自由 dict, 示例 `{"timeout_seconds": 120}`);
  - MCP 工具集待 Phase 8 落地时按 ADR 决定挂载位置 (Agent 模型扩展字段 or 声明文件)。

### 2.2 Skill = 能力声明 (独立于 Agent)

`agents/models.py` 的 `Skill` 模型 (Phase 3B),由 `SkillRegistry` 管理
(`register/get/list/remove/find_by_skill`, 事件 `skill.registered/removed/viewed`):

```python
class Skill(BaseModel):
    id: str
    name: str
    category: str = "general"
    description: str = ""
    capabilities: list[str]        # 能力点列表
    version: str = "1.0.0"
```

- Skill 是**能力声明 (Capability Catalog),非执行**:只描述"会什么",不绑定任何运行时。
- 能力匹配链路 (与 Runtime Catalog 对应): 任务 → SkillRegistry 按 `description/capabilities`
  匹配加载知识 → 派发时按 Runtime 能力 (`find_by_capability`) 选执行器。
- 完整知识结构 (frontmatter/步骤/pitfalls/验证) 见 [skill-model.md](./skill-model.md)。

### 2.3 Runtime = 执行方式 (执行器)

三层分离 (Phase 4B-1 + Phase 5A.1, ADR-0006/ADR-0014),**描述 / 身份 / 执行 三者解耦**:

| 层 | 模型 | 职责 | 代码位置 |
|:---|:-----|:-----|:---------|
| **Catalog (能力描述)** | `RuntimeDefinition` (`id/name/type/description/capabilities/supported_tasks/version/status/metadata`) | 只描述能力,供 `find_by_capability` 检索; 永不参与派发 | `runtimes/` (catalog.json + 默认定义 hermes/echo/mock) |
| **Registry (实例身份)** | `RuntimeInfo` (`id/name/type/status: AVAILABLE/DISABLED`) | 已注册实例的可用状态; `resolve_runtime_id` 派发解析 | `runtime/registry.py` |
| **Adapter (执行器)** | `RuntimeAdapter.execute(request) -> ExecutionResult` | 唯一执行出口; 具体实现 | `runtime/adapters/echo.py` (echo), `runtime/adapters/hermes.py` (subprocess hermes CLI) |

- **Core 只认 `RuntimeAdapter` 抽象接口** (architecture.md §7.1): 换 Runtime = 换 Adapter,
  Core 零改动。当前真实实现仅 `HermesRuntimeAdapter`; `EchoRuntimeAdapter` 用于测试/冒烟。
- Assignment/Execution 已按 `runtime_id` 解析 (4B-2/4B-3) → Provider 层落地后偏好即可生效。

### 2.4 Provider = LLM 来源 (Phase 8 规划)

> 状态: ⬜ 规划中 (roadmap.md Phase 8, 评审 §2 确认"Provider 层是当前最大差距")。

- **定位**: Runtime 是"执行器"(怎么跑),Provider 是"LLM 来源"(用谁的模型)。
  一个 Runtime 可对接多个 Provider (如 Hermes 后端可切 OpenAI/Anthropic/Local)。
- **规划架构** (三层: Factory → LLM Interface → Providers):

```
Factory 核心 (Task/Workflow/Orchestration/Validation)
        │  唯一执行出口 (不直连任何 LLM)
        ▼
┌──────────────────────────────────────────────┐
│  LLM Interface (协议: execute(request)→result)│
│  request: 目标/上下文/文件范围/验收标准/checkpoint│
└───────┬──────────┬──────────┬──────────┬──────┘
        ▼          ▼          ▼          ▼
   hermes-provider codex-provider openai-provider local-provider
   (subprocess CLI) (subprocess)  (HTTP API)  (HTTP/GGUF)
```

- 规划模块: `factory-core/providers/` (interface/registry/store 复用 4B-1 三段式模式),
  CLI `factory provider list|add|test|use`, 环境变量 `FACTORY_PROVIDER` + 默认提供方,
  事件 `provider.registered` / `provider.usage.started/completed/failed`。
- **边界**: Provider 是执行器,不承载决策 (决策仍归 Orchestration/人工); 未选提供方时
  行为与今日一致 (默认 hermes, 向后兼容)。

---

## 3. 关系图

```
                        ┌──────────────────────────────┐
                        │        ProjectDefinition      │
                        │  runtime_preferences (Phase 6A)│
                        │    per-role 偏好路由           │
                        └──────────────┬───────────────┘
                                       │ 按 role 解析
┌──────────┐  skills (引用)  ┌─────────▼─────────┐   runtime_id  ┌──────────────┐
│ Skill     │ ◀───────────── │       Agent        │ ────────────▶ │   Runtime     │
│ Registry  │                │ (角色配置实例)       │               │   Registry    │
│ (能力声明) │                │ role + skills +    │               │  (实例身份)    │
└──────────┘                │ mcp_tools* + runtime_pref │       └──────┬───────┘
                            └─────────────────────┘                  │ 执行
                                    │ 委派 (Assignment/Execution)    ▼
                                    ▼                        ┌──────────────┐
                            ┌──────────────┐   provider_id   │  Runtime      │
                            │  Orchestration│ ──────────────▶ │  Adapter      │
                            │  (调度/验证)   │                 │  (执行器)      │
                            └──────────────┘                 └──────┬───────┘
                                                                    ▼
                                                          ┌──────────────────┐
                                                          │  Provider (Phase 8)│
                                                          │  OpenAI/Anthropic/ │
                                                          │  Local (LLM 来源)  │
                                                          └──────────────────┘
```

*`mcp_tools` 为规划字段 (Phase 8 落地)。

**执行链路** (现状已通, Provider 层待 Phase 8):
`任务 → 委派 (role) → Assignment/Execution 按 runtime_id 解析 → RuntimeAdapter.execute →
(Phase 8: Provider) → 结构化结果 → 独立验证 (validation-model 双验证)`。

---

## 4. 声明示例 (YAML)

### 4.1 per-role runtime 偏好 (Phase 6A 已建字段, Phase 8 生效)

评审 §2 设计建议: 同一项目内按角色路由到不同 Provider —
架构决策 → Claude, 编码 → Codex, 验证/测试 → Hermes。

```yaml
# project.yaml (ProjectDefinition.runtime_preferences, Phase 6A 已建)
id: scorepocket
name: ScorePocket
runtime_preferences:          # per-role 偏好路由 (Assignment/Execution 按 runtime_id 解析)
  architect:  { provider: claude }   # 架构决策 → Claude (Anthropic)
  developer:  { provider: codex }    # 编码 → Codex (OpenAI)
  tester:     { provider: hermes }   # 验证/测试 → Hermes (本地 CLI)
```

### 4.2 Agent 声明 (现状模型 + 规划字段)

```yaml
# roles/ 注册表 (agent-model §4) + agents/ 注册 (Phase 3B)
agent:
  id: architect-1
  name: 架构师
  role: architect
  skills: [architecture, state-machine-semantics]   # SkillRegistry 引用
  # --- 规划字段 (Phase 8 落地) ---
  mcp_tools: [github, jira]           # MCP 工具集 (mcp/ 层, 未实现)
  runtime_preferences: { provider: claude }   # 或上移到 ProjectDefinition 按项目声明
```

### 4.3 Skill 声明 (现状)

```yaml
# skills/<category>/<name>/SKILL.md (skill-model §2)
name: architecture
category: software-development
description: 架构审计: 根因分析、设计决策、推荐改动方案…
trigger: 当任务需要定义或评估架构方案时…
capabilities: [root-cause-analysis, design-decision, impact-assessment]
```

### 4.4 Runtime 定义 (现状, Runtime Catalog)

```json
// runtimes/catalog.json (Phase 5A.1) — 能力描述层
{ "id": "hermes", "name": "Hermes CLI", "type": "agent",
  "capabilities": ["code-generation", "tool-use", "reasoning"],
  "supported_tasks": ["feature-implementation", "bug-fix"] }
```

---

## 5. 与 Core 的边界

**边界原则 (冻结 §一)**: Core = 通用原语 (状态/流程/事件/验证/抽象), **Core 零领域依赖**;
Extension = 领域能力, 经 Skill/MCP/Runtime/Provider **声明式注册**接入。

| 领域 | 类型 | 接入方式 | 是否改 Core |
|:-----|:-----|:---------|:-----------:|
| Git / GitHub | Integration | Skill / MCP | 否 (Core 零 Git 依赖) |
| Jira / Figma / AWS / Database | 外部工具 | MCP | 否 |
| Market Research / UI Generation / Office / SEO | 能力 | Skill | 否 |
| Monitoring / Incident | 运营 | Operations Layer (Phase 10) | 否 |
| 具体 LLM (OpenAI/Claude/Local) | 模型来源 | Provider (Phase 8) | 否 |

> **新增任何能力不修改 Core**: OpenClaw skill / Codex plugin / MCP server /
> 第三方 Agent = 声明式注册 (JSON) — 见 §6。

---

## 6. 未来扩展 (声明式接入)

全部走"注册表 + 声明文件 + 事件"既有模式,Core 不改一行:

| 扩展 | 接入方式 | 复用机制 |
|:-----|:---------|:---------|
| **OpenClaw skill** | 翻译/适配为 `Skill` 声明 (frontmatter 五段式), 注册进 SkillRegistry | skill-model §4 (草拟→登记→试用→沉淀) |
| **Codex plugin** | 注册为 `RuntimeDefinition` + 对应 `RuntimeAdapter` 实现 (或 Codex Provider, Phase 8) | 5A.1 Catalog + 4B-1 Adapter 接口 |
| **第三方 Agent** | 声明式注册 (JSON): role + skills + mcp_tools + runtime 偏好 → 写入 agents/ 注册表 | 3B AgentRegistry + 4B-3 Matcher (role/skill/AVAILABLE) |
| **MCP server** | `mcp/` 层声明工具端点, Agent 按需挂载 | Phase 8 规划 (评审 §2 差距表) |
| **新 LLM 提供方** | 实现 Provider 适配器 + `provider list/add` 注册 | Phase 8 providers/ 三层模式 |

**扩展步骤模板** (与 agent-model §4.1 新增角色接口一致):
1. 起草声明 (Skill / RuntimeDefinition / Agent JSON);
2. 登记进对应注册表 (SkillRegistry / Runtime Catalog / AgentRegistry);
3. 试用一个真实任务, 验证匹配与执行;
4. 沉淀: 更新注册表索引与文档, 回写新 pitfall。

---

## 7. 现状 vs 目标差距表

| 要素 | 目标 (冻结模型) | 现状 | 差距 → 落地阶段 |
|:-----|:----------------|:-----|:----------------|
| Agent | 角色 + skill 集 + MCP 工具集 + runtime 偏好 | role + skills ✅; mcp_tools ❌; runtime 偏好挂在 ProjectDefinition ✅ | Phase 8 挂载 mcp_tools/偏好字段 |
| Skill | 独立能力声明 | ✅ SkillRegistry (category/capabilities) | — |
| MCP | 外部工具层 | ❌ `mcp/` 目录空 | Phase 8 新增层 |
| Runtime | 执行方式抽象 | ✅ RuntimeAdapter (echo/hermes) + Catalog | 需 per-agent runtime 偏好生效 |
| Provider | LLM 来源 | ❌ Hermes 硬绑定 | **Phase 8 核心** |

下一份文档: approval-model.md(人工审核节点如何建模)。
