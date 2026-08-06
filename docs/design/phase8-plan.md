# Phase 8 Plan — LLM Provider Abstraction

> 日期: 2026-08-06 | 状态: 架构设计评审, 待确认
> 冻结约束: Core 零修改 / 2310 tests 不受影响 / Hermes 保持可用 / 新 Provider 不修改 Core / Provider 可移除

## 1. 架构评审 — 7 个问题

### Q1: Provider Layer 位置

**factory-core/providers/** — 独立 Extension, 与 runtime/ 平级。

理由:
- **Runtime 与 Provider 必须分离** (Rule 1): runtime/ = 执行机制; providers/ = 智能来源
- 模块独立性 (Composable Capability): providers/ 独立目录/测试/数据空间, 删除不影响 Core
- 对称: runtimes/ (Runtime Catalog) 已存在 → providers/ (Provider Catalog) 同模式

```
factory-core/runtime/      执行机制 (RuntimeAdapter: hermes/echo)  [已有]
factory-core/runtimes/     Runtime Catalog                         [已有]
factory-core/providers/    智能来源 (ProviderAdapter: hermes/openai/claude/local)  [Phase 8 新]
```

### Q2: 最终架构关系

```
Agent (角色配置)
  ├── Skills (能力声明)
  ├── MCP (外部工具, 未来)
  └── Runtime (执行机制) ──→ Provider (智能来源) ──→ Model (GPT/Claude/Gemini/Local)
       │                        │
       │                        └── ProviderAdapter 统一接口
       └── 兼容路径: HermesRuntimeAdapter 自带执行 (保留, 不经 Provider)

配置驱动 (project.yaml runtime_preferences):
  development:   { runtime: hermes,   provider: openai }
  documentation: { runtime: claude-runtime, provider: claude }
  local:         { provider: ollama }
```

### Q3: Runtime 调 Provider 接口

```python
class ProviderAdapter(ABC):
    """统一智能接口 — 不绑定具体 API"""
    id: str
    def generate(self, request: ProviderRequest) -> ProviderResponse: ...   # 同步
    def chat(self, messages: list[dict]) -> ProviderResponse: ...            # 对话
    def stream(self, request: ProviderRequest) -> Iterator[ProviderResponse]: ...  # 流式
```

- ProviderRequest/ProviderResponse = Pydantic 统一 I/O (prompt/messages/model/params → content/tokens/usage/error)
- Runtime 经 ProviderRegistry 解析 Provider → 调统一接口; 不直接接触 OpenAI/Claude API 差异

### Q4: 兼容性策略

- **HermesRuntimeAdapter 零改动** (现有 2310 测试覆盖的执行路径不动)
- Provider 层纯新增: 现有 workflow 不经 Provider 继续工作
- Hermes 双角色: 既有 Runtime Adapter (执行) + 新 Hermes Provider Adapter (智能, 调 hermes CLI -z 或 API)
- 迁移: runtime_preferences.provider 配置后, ExecutionRunner 可选注入 Provider (默认不注入 = 原行为)

### Q5: Provider 选择优先级

```
1. 显式项目配置   project.yaml runtime_preferences.<task_type>.provider
2. Agent 要求     Agent.runtime_preferences (角色级)
3. Runtime 能力   Runtime 声明的默认 provider
4. 默认 provider  ProviderRegistry.default
```
配置驱动, 无硬编码选择逻辑。

### Q6: Event

```
生命周期:  provider.registered / provider.removed / provider.viewed
执行:      provider.selected / provider.execution.started / provider.execution.completed / provider.execution.failed
经 EventLogger (唯一事实源)
```

### Q7: 持久化边界

| 数据 | 位置 | 说明 |
|:-----|:-----|:-----|
| Provider Catalog (定义) | .factory/providers/catalog.json | 独立数据空间 (与 runtimes catalog 同模式) |
| Provider 配置 (偏好) | project.yaml runtime_preferences | 已有字段 (Phase 6A) |
| Provider 实例 | 不持久化 | Registry 运行时 |

## 2. 模块边界

```
factory-core/providers/
├── models.py       ProviderDefinition + ProviderRequest/Response + ProviderStatus
├── provider.py     ProviderAdapter 抽象接口 (generate/chat/stream)
├── registry.py     ProviderRegistry (register/get/list/remove/find_by_capability + default)
├── store.py        catalog.json 原子写 (独立数据空间 .factory/providers/)
├── adapters/
│   ├── hermes.py   Hermes Provider (调 hermes CLI/API)
│   ├── openai.py   OpenAI Provider (API 客户端, 配置化)
│   ├── claude.py   Claude Provider (预留)
│   └── local.py    Local LLM (ollama 等, 预留)
└── __init__.py
```

## 3. 数据模型

```python
class ProviderDefinition(Pydantic):
    id: str; name: str; type: str          # cloud/local/agent
    capabilities: list[str]                # chat/generation/code/vision...
    version: str; status: str              # ACTIVE/DISABLED
    config_schema: dict                    # 配置项描述 (api_key 引用/env/endpoint)

class ProviderRequest(Pydantic):
    provider_id: str; task: str
    prompt: str | None; messages: list[dict] | None
    model: str | None; params: dict

class ProviderResponse(Pydantic):
    provider_id: str; content: str
    tokens: dict | None; error: str | None
```

## 4. 接口

```
ProviderRegistry: register/get/list/remove/find_by_capability/set_default/resolve
ProviderAdapter: generate/chat/stream (抽象)
ExecutionRunner 集成 (可选注入): runtime_preferences.provider → resolve → adapter.generate
CLI: factory provider list / add / remove / test <id>
```

## 5. 配置模型

```yaml
# project.yaml (runtime_preferences 已有字段, Phase 8 生效)
runtime_preferences:
  development:   { runtime: hermes, provider: openai }
  documentation: { runtime: claude-runtime, provider: claude }
  local:         { provider: ollama }
```

## 6. 迁移策略

```
Phase 8a: providers/ 基础 — 模型 + Registry + catalog + 事件 + 默认 hermes provider (纯新增)
Phase 8b: ProviderAdapter 接口 + adapters (hermes 实现 + openai/claude/local 占位)
Phase 8c: Runtime 集成 — runtime_preferences.provider → ExecutionRunner 可选注入 + CLI (provider list/add/test)
兼容: 原 HermesRuntimeAdapter 路径保留 (默认不经 Provider)
```

## 7. 测试策略

- Provider 模型/Registry/Persistence (catalog 原子写/独立数据空间)
- 选择优先级 (显式 > Agent > Runtime > default)
- ProviderAdapter 接口契约 (generate/chat/stream + Mock adapters)
- CLI (list/add/remove/test + 退出码 + 事件)
- 事件流 (registered/selected/execution.*)
- 兼容性: 现有 Hermes 执行路径回归 (2310 不破坏)
- 删除 Provider 不影响 Factory (Composable Capability 判断标准)

## 8. 确认要点

1. ✅ Core 不变 (providers/ 纯新增, 零 Core 修改)
2. ✅ 2310 tests 不受影响 (HermesRuntimeAdapter 零改动)
3. ✅ Hermes 保持可用 (双角色: Runtime Adapter + Provider Adapter)
4. ✅ 新 Provider 不修改 Core (声明式注册: adapters/ + registry)
5. ✅ Provider 可移除 (独立数据空间, 删除不影响 Factory)

## 非目标

不实现: Product Intelligence / PRD 生成 / UI 生成 / Experience System / Self Extension (后续 Phase)
