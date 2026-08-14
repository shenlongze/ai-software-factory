# S10-028 Task 003 — Extension Contract

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 只设计接口,不实现插件系统
> 目标:定义未来扩展契约,使模块独立产品时无需重构

---

## 1. 设计原则

1. **契约稳定,实现可插拔** — Extension 依赖契约(接口),不依赖具体实现
2. **manifest 声明,entrypoint 加载** — 每个扩展有声明文件 + 加载入口
3. **最小权限** — 扩展声明权限,运行时校验(与 Skill 权限链同哲学)
4. **失败安全** — 扩展加载失败不影响内核
5. **注册即发现** — 现有注册表模式(DoctorCheck/ServiceDef/Skill)泛化

## 2. 通用 Extension Manifest

```python
# 未来 extension manifest (每个扩展的声明)
{
  "id": "af.ext.rag.engine",          # 全局唯一 id (af.ext.<type>.<name>)
  "name": "RAG Engine",
  "version": "1.0.0",
  "type": "rag",                       # agent|skill|router|rag|governance|evaluation|provider|ui
  "entrypoint": {                      # 加载入口
    "module": "rag_engine.plugin",
    "class": "RagEnginePlugin"
  },
  "capabilities": ["index", "retrieve", "embed"],   # 声明能力
  "permissions": [                     # 最小权限
    {"read": ["~/.factory/projects"]},
    {"write": ["~/.factory/rag-index"]}
  ],
  "dependencies": [                    # 依赖
    {"id": "af.kernel", "version": ">=1.0"},
    {"id": "af.ext.provider", "version": ">=1.0"}
  ],
  "config_schema": {...}               # 配置 JSON Schema
}
```

## 3. 各类型 Extension Contract

### 3.1 Agent Extension

```python
class AgentExtension:
    """执行者扩展 — 提供 Agent 实现。"""

    manifest: ExtensionManifest

    def create(self, agent_id: str, skills: list[str],
               ctx: ExtensionContext) -> AgentHandle:
        """创建 Agent 实例 (绑定技能)。"""

    def execute(self, handle: AgentHandle,
                request: ExecutionRequest) -> ExecutionResult:
        """执行任务 (Kernel Runtime 壳调用, 不关心实现)。"""
```

### 3.2 Skill Extension

```python
class SkillExtension:
    """能力包扩展 — 提供 Skill 注册。"""

    manifest: ExtensionManifest

    def register(self) -> list[SkillDefinition]:
        """声明本扩展提供的 Skills (工具/权限/指令打包)。"""

    def invoke(self, skill_id: str, input: dict,
               ctx: ExtensionContext) -> SkillResult:
        """执行 Skill (经权限链校验后)。"""
```

### 3.3 Router Extension

```python
class RouterExtension:
    """决策源扩展 — 提供新的路由决策层 (Router 核心五层链冻结)。"""

    manifest: ExtensionManifest

    def suggest(self, task: TaskContext,
                candidates: list[ModelChoice]) -> RouterSuggestion | None:
        """在既有候选上叠加建议 (source 标识扩展层)。

        RouterSuggestion: {
            model_id, provider_id,
            score, reasons, source  # source = extension id
        }
        """
```

### 3.4 RAG Extension

```python
class RAGExtension:
    """知识引擎扩展。"""

    manifest: ExtensionManifest

    def index(self, project: ProjectRef, source: ProjectSource) -> IndexResult:
        """项目导入 → 建索引。"""

    def retrieve(self, query: str, project: ProjectRef,
                 ctx: ExtensionContext) -> list[Chunk]:
        """检索 (embedding/retriever 实现可换)。"""
```

### 3.5 Governance Extension

```python
class GovernanceExtension:
    """治理策略扩展。"""

    manifest: ExtensionManifest

    def evaluate(self, action: ActionContext) -> GovernanceDecision:
        """审批策略: 允许/拒绝/需人工。

        GovernanceDecision: {verdict, reason, required_approval}
        """
```

### 3.6 Evaluation Extension

```python
class EvaluationExtension:
    """评估器扩展。"""

    manifest: ExtensionManifest

    def evaluate(self, artifact: Artifact,
                 criteria: list[str]) -> EvaluationResult:
        """按维度评估产出 (质量分/证据)。"""
```

### 3.7 Provider Extension

```python
class ProviderExtension:
    """模型源扩展 (已实现 — OpenAI/Anthropic/DeepSeek/Ollama)。"""

    manifest: ExtensionManifest

    def create_adapter(self, config: ProviderConfig) -> ProviderAdapter:
        """按配置创建 Provider Adapter (generate/chat/stream)。"""
```

## 4. ExtensionContext(扩展运行时上下文)

```python
class ExtensionContext:
    """扩展可用的内核能力 (最小面, 不暴露内核内部)。"""

    def emit_event(self, type: str, payload: dict) -> None:
        """写审计事件 (经 Kernel Event)。"""

    def get_config(self, section: str) -> dict:
        """读配置 (经 Kernel Config, 只读)。"""

    def resolve_identity(self) -> Identity:
        """当前身份 (经 Kernel Identity)。"""
```

## 5. Extension Manager(未来, 设计)

```
Plugin Manager:
  discover:  扫描 extensions/ 目录 → 解析 manifest
  validate:  manifest 校验 (schema + 权限声明 + 依赖解析)
  load:      entrypoint → 实例化 → 注册到对应 Registry
  lifecycle: enable/disable/reload (热插拔可选)
  sandbox:   权限执行 (经 Governance)
```

## 6. 契约稳定性保证

1. **契约 = Python Protocol/抽象基类**(现有 DoctorCheck/ServiceDef 模式)
2. **版本兼容**:manifest 声明支持的内核版本;契约变更 = 主版本升级
3. **不破坏性扩展**:新方法加默认实现;旧扩展不因新契约方法崩溃
4. **接口最小化**:ExtensionContext 只暴露 emit_event/get_config/resolve_identity — 扩展无法碰内核内部

## 7. 与现有代码的映射(已存在的"准契约")

| 现有 | 对应未来 Contract | 差距 |
|---|---|---|
| DoctorCheck {id, label, run()} | 诊断扩展(通用契约) | 加 manifest |
| ServiceDef {id, start, stop, status} | 服务扩展 | 加 manifest |
| SkillRegistry / Skill 模型 | SkillExtension | 加 manifest + invoke |
| MCP Adapter | 外部工具协议(可视为 Provider/Tool 扩展) | 已符合 |
| ProviderInterface | ProviderExtension | 已符合 |
| ModelChoice / ProviderSelection | Router 扩展输出类型 | 已预留 source/reason/score |

**结论:现有代码已 80% 符合 Extension Contract 模式;未来只需加 manifest + 统一管理。**

## 8. 为什么这样设计(独立产品化保障)

| 需求 | 契约如何保障 |
|---|---|
| Router 独立成产品 | RouterExtension 契约 → 独立实现,内核五层链仍可用 |
| Governance 独立 | GovernanceExtension 契约 → 策略可插拔 |
| RAG 用外部向量库 | RAGExtension 契约 → Chroma/Qdrant 各自实现 |
| 新 Agent 供应商 | AgentExtension 契约 → 注册即用 |
| 不重构 | 契约冻结 = 模块边界冻结;独立产品只是新实现同一契约 |

---

> Task 003 完毕 | Extension Contract 设计完成 | 只设计接口,未实现
