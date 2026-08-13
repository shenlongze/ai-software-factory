# S10-022 Phase 2A 设计 Review — Model Catalog v1

> 日期:2026-08-13 | 状态:待确认 | 前置:S10-021 Phase 1 ✅ (c1c535f)
> 范围:Model Catalog 数据基础(不实现智能推荐/动态权重/历史学习/自动优化)
> 战略:为最终 LLM Smart Router 建立模型数据基础

---

## 1. 现状(真实代码取证)

| 已有 | 位置 | 说明 |
|---|---|---|
| Provider 两级骨架 | factory-console/llm_control.py | ProviderConfig.models 是 **裸字符串列表**(如 ["deepseek-v4-pro"]) |
| Provider 级能力画像 | factory-core/providers/capability.py | ProviderCapabilityProfile(matrix: 能力→质量分)— provider 级,非模型级 |
| Provider 级定义 | factory-core/providers/models.py | ProviderDefinition.models 也是字符串列表 |
| TaskRequirement | factory-core/providers/models.py:143 | required_capabilities/min_quality/budget 已有 |

**关键缺口:模型级结构(ModelInfo)完全不存在** — 无 context_window/cost/enabled 的模型元数据,
"哪个模型适合该任务"无法回答(只有 provider 级画像,且与执行链无接线)。

## 2. 设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 新增独立模块 `factory-console/model_catalog.py`(ModelCatalog),与 llm_control.py 并列 | Phase 1 模式复用;不碰 factory-core/providers(冻结);职责单一 |
| D2 | 落盘 `~/.factory/models.json`(独立于 providers.json) | 数据空间分离;模型目录与 provider 配置解耦 |
| D3 | 模型归属校验:register 时 provider_id 必须存在于 ControlPlane(宽松:仅警告不阻断,或校验存在) | 保持 Provider→Model 两级结构一致性 |
| D4 | ModelInfo.enabled 与 ProviderConfig.enabled 独立 | 模型级开关(Provider 开但某模型禁);Router 兼容 |
| D5 | suggest() 返回 ModelChoice 列表(排序+理由),非单个"最佳" | 不实现智能推荐;只做确定性过滤+排序,Router 将来接管 |
| D6 | 复用 TaskRequirement 概念但不强制依赖 factory-core | 接口参数直接接收 required_capabilities/min_quality/budget,避免跨包耦合 |

## 3. 数据模型(model_catalog.py, pydantic)

```python
class ModelCost(BaseModel):
    input_per_1k: float | None = None      # USD / 1K tokens
    output_per_1k: float | None = None

class ModelInfo(BaseModel):
    model_id: str                          # 唯一键 (如 "deepseek-v4-pro")
    provider_id: str                       # 归属 provider (必须存在)
    capabilities: list[str] = Field(default_factory=list)  # code/reasoning/chat/vision/tool-use
    context_window: int | None = None      # tokens
    cost: ModelCost = Field(default_factory=ModelCost)
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展 (max_output_tokens/发布日期等)

class ModelCatalogFile(BaseModel):
    version: int = 1
    models: dict[str, ModelInfo] = Field(default_factory=dict)

# ---- Router 兼容预留 (Phase 4 复用, 字段兼容扩展) ----
class ModelChoice(BaseModel):
    model_id: str
    provider_id: str
    score: float | None = None       # 当前 = 能力命中率 (0-1); 未来 Router 加权
    reasons: list[str] = Field(default_factory=list)  # 为什么候选 (能力命中/成本/上下文)
    source: str = "model-catalog"    # 决策来源 (v1: model-catalog; 未来: router)
```

## 4. 接口设计(model_catalog.py)

```python
class ModelCatalog:
    def __init__(self, models_file: str | Path | None = None,
                 control_plane: LLMControlPlane | None = None): ...
        # models_file 缺省 ~/.factory/models.json; control_plane 可选 (D3 校验 + provider enabled 过滤)

    # ---- 持久化 (同 llm_control 模式: 原子写 + 损坏响亮错误) ----
    def load(self) -> ModelCatalogFile
    def save(self, data: ModelCatalogFile) -> None
    def reload(self) -> ModelCatalogFile

    # ---- 注册/变更 ----
    def register(self, model: ModelInfo) -> ModelInfo        # 新增或覆盖 (provider 存在校验)
    def unregister(self, model_id: str) -> bool              # 删除
    def set_enabled(self, model_id: str, enabled: bool) -> ModelInfo
    def list_models(self, *, include_disabled: bool = False) -> list[ModelInfo]

    # ---- 查询 ----
    def get_model(self, model_id: str) -> ModelInfo | None
    def find_by_capability(self, capability: str, *, enabled_only: bool = True) -> list[ModelInfo]
    def models_by_provider(self, provider_id: str) -> list[ModelInfo]

    # ---- Agent 侧查询: "哪个模型适合该任务" (v1: 确定性过滤+排序, 非智能推荐) ----
    def suggest(self, *, required_capabilities: list[str] | None = None,
                min_quality: float = 0.0, max_cost_per_1k: float | None = None,
                min_context_window: int | None = None,
                provider_id: str | None = None) -> list[ModelChoice]:
        # 过滤: enabled=True + (provider 在 ControlPlane 中 enabled, 若 control_plane 提供)
        #        + 所有 required_capabilities 命中 + 成本上限 + 上下文窗口下限
        # 排序: 能力命中数降序 → cost 升序 → model_id 字典序 (确定性)
        # 返回 ModelChoice 列表 (score=命中率, reasons 含每条过滤理由)
```

## 5. 修改范围

### 新增文件
1. `factory-console/model_catalog.py`(~300 行)
2. `tests/llm/test_model_catalog_persistence.py`(~15 cases)— 持久化/损坏/注册/启停
3. `tests/llm/test_model_catalog_query.py`(~15 cases)— 查询/能力过滤/suggest 排序
4. `tests/llm/test_model_catalog_router_compat.py`(~8 cases)— ModelChoice 字段兼容/provider 校验

### 修改文件
5. `factory-console/llm_control.py` — **最小**:仅新增 `models()` 访问器暴露 ProviderConfig.models 供 ModelCatalog 校验?不,无需修改——ModelCatalog 构造时已可读 ControlPlane 公开接口。**保持零修改**。(若 register 校验需要,通过已有 get_provider() 即可,无需改 llm_control.py)

### 不动
- factory-core/providers/ 全部(selector/capability/models — 冻结)
- factory-exec/exec/ 全部
- factory-console/config.py、service.py、workflow_runner.py(Phase 2A 不接线执行链,只建数据基础)
- 不实现:动态权重/历史学习/自动优化/Router

## 6. 验收标准映射

| 验收 | 验证方式 |
|---|---|
| A. Provider→Model 两级结构 | models.json 中 model.provider_id 指向 providers.json 中的 provider;测试断言两级一致 |
| B. 模型信息结构化 | ModelInfo 全字段 (model_id/provider_id/capabilities/context_window/cost/enabled) 测试覆盖 |
| C. 注册/查询/按能力过滤 | register/unregister/find_by_capability 测试 |
| D. Agent 查询接口 | suggest() 返回 ModelChoice 列表 (score/reasons/source),确定性排序测试 |
| E. 重启持久化 | save → 新实例 reload 往返一致 |
| F. Router 兼容预留 | ModelChoice {model_id, provider_id, score, reasons, source} 字段测试;不实现 router 逻辑 |

## 7. 内置默认模型目录(注册到 models.json 的种子数据)

> 真实性铁律(用户要求 5):真实可调用模型使用真实 API 名称;不确定/未验证可调用的
> 模型一律标记 metadata.placeholder=true + metadata.evidence 说明来源,绝不冒充真实模型。

| model_id | provider | capabilities | context_window | cost in/out per 1k | 真实性 |
|---|---|---|---|---|---|
| deepseek-chat | deepseek | code, chat | 64000 | 0.00028 / 0.00042 | ✅ 真实 (DeepSeek API) |
| deepseek-reasoner | deepseek | reasoning, code | 64000 | 0.00055 / 0.00219 | ✅ 真实 (DeepSeek API) |
| gpt-4o | openai | code, chat, vision | 128000 | 0.0025 / 0.01 | ✅ 真实 (OpenAI API) |
| claude-sonnet-4 | anthropic | code, reasoning, chat | 200000 | 0.003 / 0.015 | ⚠️ 系列名真实, 精确版本未验证 → placeholder=true + evidence 注明 |

> - 种子在首次 load 缺失文件时写入(内置默认,不硬编码查询逻辑)
> - 费率与 config.py PROVIDER_DEFAULTS 对齐(deepseek-chat 对应 deepseek 默认费率)
> - placeholder 模型在 suggest() 中默认仍可返回,但 ModelChoice.reasons 注明 "placeholder model"
> - metadata 结构:{"placeholder": bool, "evidence": "vendor docs / verified 2026-08"}

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 与 factory-core capability 语义重复 | 不合并;model_catalog 是模型级数据基础,capability 是 provider 级画像;Router 阶段再统一 |
| 种子数据过期(费率变化) | 存 metadata.evidence 来源;费率可 set/覆盖 |
| suggest() 被误当"智能推荐" | 文档明确:v1 是确定性过滤+排序,非学习;reasons 全部可解释 |
| 破坏 Phase 1 | llm_control.py 零修改;全量回归门 |

## 9. 实施顺序

1. model_catalog.py + 3 测试文件(纯新增)
2. 定向测试绿 → 全量 pytest 回归
3. 冒烟:注册种子 → 重启 → 查询 suggest("code") 返回 ModelChoice
4. commit + push + completion 报告

---

> 设计 Review 完毕 | 待确认后开始实现
