# AI Factory OS — 目标架构（SSoT v0.2，冻结）

> 状态: **冻结** | 改动需显式裁决 | 上一版: `docs/archive/architecture-v0.1.md`

## 一、七层结构

| 层 | 职责 | 允许依赖 |
|----|------|---------|
| `contracts/` | 全部跨层契约（Protocol / dataclass / 错误），无实现 | 仅标准库 |
| `core/` | 内核六段（会话/能力/调度/节点/事件/Gate），只放契约与默认实现 | `contracts/` |
| `services/` | OS 服务（组织/项目/工作/执行/治理/审计/可观测/学习/记忆/知识…） | `contracts/` |
| `plugins/` | 一切扩展（factories/agents/skills/tools/mcp/models/connectors/controllers/healers） | `contracts/` |
| `infrastructure/` | 技术底座（storage/sandbox/llm/messaging/process），与 OS 语义无关 | `contracts/` |
| `api/` | 对外接口层（DTO / 路由装配） | `contracts/` |
| `bootstrap/` | 装配与启动（唯一可 import 全局） | 全部 |

**`apps/` 独立于 `src/`，不在包内**（cli / web / desktop / mobile 作为消费者）。

## 二、根契约（8 个 + 5 个）

**8 个根契约**：`identity` · `organization` · `project` · `work` · `execution` · `governance` · `events` · `errors`

**5 个内核契约**：`conversation` · `capability` · `scheduler` · `node` · `plugin`

## 三、依赖铁律（8 条）

| # | 规则 |
|---|------|
| R1 | `contracts/*` 不许 import `ai_factory_os` 下其他顶层包 |
| R2 | `core/*` 只许 import `contracts`（+ 标准库） |
| R3 | `services/A` 不许 import `services/B` 的**实现**（只许 import 其契约） |
| R4 | `plugins/*` 只许 import `contracts` |
| R5 | `infrastructure/*` 只许 import `contracts` |
| R6 | `api/*` 不许 import `infrastructure.storage` 的具体实现 |
| R7 | `apps/*` 不许出现在 `src/` 内（apps 独立） |
| R8 | `bootstrap/*` 例外（可 import 全部） |

## 四、目录树（冻结版）

```
src/ai_factory_os/
├── contracts/     identity organization project work execution governance events errors
├── core/          conversation capability scheduler node events gate
├── services/      identity organization project work planning execution governance
│                  audit observability operations learning memory knowledge workspace
├── plugins/       factories agents skills tools mcp models connectors
│                  controllers/{browser,computer} healers
├── infrastructure/ storage sandbox llm messaging process
├── api/
└── bootstrap/

apps/   cli web desktop mobile          （独立于 src/）
tests/  contracts architecture services integration e2e
```

## 五、术语

| 术语 | 含义 |
|------|------|
| **Node** | 执行节点（自治原语） |
| **Capability** | 能力（抽象"谁能做"，经解析绑定插件） |
| **Extension** | 扩展/插件（提供具体能力实现） |
| **Conversation** | 会话（唯一业务入口） |
| **Projection** | 投影（只读呈现，零事实源） |
| **WorkItem** | 工作项（Project 下可执行单元） |
| **Run** | 一次执行实例（Execution 的记录） |
