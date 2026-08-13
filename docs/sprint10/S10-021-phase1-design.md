# S10-021 Phase 1 设计 Review — LLM Control Plane v1 (Rev 2 — 用户确认版)

> 日期:2026-08-13 | 状态:✅ 已确认 (Rev 2) | 前置:docs/sprint10/S10-021-reality-check.md
> 范围:Provider 配置持久化 + Credential 管理 + Runtime 接线(不实现 Router,不动 selector.py)
> Rev 2 变更:按用户 5 条额外约束调整 —— ① Provider 不绑单模型(Provider→Models→RouterDecision 兼容)
> ② api_key_ref 禁明文 ③ Runtime 无固定模型/Provider 耦合 ④ 预留 Routing Decision 扩展字段
> ⑤ 增加真实装配链验证(providers.json→ControlPlane→workflow_runner→Provider 实例)

---

## 1. 设计决策摘要

| # | 决策 | 理由 |
|---|---|---|
| D1 | 新增独立模块 `factory-console/llm_control.py`(LLMControlPlane),不塞进现有 config.py | 职责单一;config.py 是只读分层读取,Control Plane 是读写管理面,分离避免污染 |
| D2 | providers.json 存 `~/.factory/providers.json`(非 providers/catalog.json) | 用户指定格式;与 factory-core 的 catalog.json(从未落盘)隔离,零冲突 |
| D3 | api_key_ref 格式沿用现有 `env:VAR` 语义(config.py:_resolve_env_ref 已实现) | 复用既有约定,不发明新语法 |
| D4 | 优先级:进程 env > 项目 .env > config.json > **providers.json** > 内置默认 | 显式运维配置优先,providers.json 是新的可持久化管理面 |
| D5 | 不动 factory-core/providers/(store/registry/selector/models) | 那套是 Phase 8A/8B 目录抽象,与 exec 执行链无接线;本轮不合并 |
| D6 | 不动 exec/provider.py、openai.py、anthropic.py、agent_runtime.py、execution_loop.py | 用户禁止范围;Adapter 已就绪零改动 |
| D7 | enabled 状态用独立 bool 字段(不进 ProviderDefinition.status) | 避免改 core models 触达冻结约束;ControlPlane 自持配置模型 |
| D8 | 日志脱敏:key 本体永不入 logger;只记录 ref 与是否存在 | 用户禁止明文日志 |

## 2. 数据模型

### providers.json(落盘格式,~/.factory/providers.json)

```json
{
  "version": 1,
  "providers": {
    "deepseek": {
      "enabled": true,
      "models": ["deepseek-v4-pro", "deepseek-reasoner"],
      "base_url": "https://api.deepseek.com/v1/chat/completions",
      "api_key_ref": "env:DEEPSEEK_API_KEY",
      "metadata": {
        "display": "DeepSeek",
        "input_rate_per_1k": 0.00028,
        "output_rate_per_1k": 0.00042
      }
    },
    "openai": {
      "enabled": false,
      "models": ["gpt-4o"],
      "base_url": "https://api.openai.com/v1/chat/completions",
      "api_key_ref": "env:OPENAI_API_KEY",
      "metadata": {}
    }
  }
}
```

### Python 模型(新增于 llm_control.py,用 pydantic BaseModel)

```python
class ProviderConfig(BaseModel):
    id: str                          # provider id (deepseek/openai/anthropic/ollama)
    enabled: bool = False
    models: list[str] = Field(default_factory=list)  # 多模型列表,不绑单模型 (Router Decision 兼容)
    base_url: str | None = None      # None → 用内置默认
    api_key_ref: str | None = None   # env:VAR 或空 (ollama 可空);只存引用,不存明文
    metadata: dict[str, Any] = Field(default_factory=dict)  # 扩展字段 (费率/display/未来路由元数据)

class ProviderConfigFile(BaseModel):
    version: int = 1
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)

# ---- Routing Decision 预留结构 (Phase 4 复用,字段兼容扩展) ----
class ProviderSelection(BaseModel):
    provider_id: str
    model_id: str | None = None
    source: str = "control-plane"    # 决策来源 (用户指定/项目规则/系统推荐/默认/control-plane)
    reason: str = ""                 # 决策理由
    score: float | None = None       # 未来 Router 打分 (当前 None)
```

## 3. 接口设计(llm_control.py)

```python
class LLMControlPlane:
    """Provider 配置管理面:持久化 providers.json + 解析 + 装配决策。"""

    def __init__(self, providers_file: str | Path | None = None,
                 environ: Mapping[str, str] | None = None,
                 config: ConfigProvider | None = None): ...

    # ---- 持久化 ----
    def load(self) -> ProviderConfigFile          # 原子读;缺失 → 空文件;损坏 → 响亮错误
    def save(self, data: ProviderConfigFile)      # 原子写 (tmp + os.replace,复用 store.py 模式)
    def reload(self) -> ProviderConfigFile        # 重读 (重启恢复验证入口)

    # ---- 查询 ----
    def list_providers(self) -> list[ProviderConfig]
    def get_provider(self, provider_id: str) -> ProviderConfig | None
    def enabled_providers(self) -> list[ProviderConfig]
    def is_enabled(self, provider_id: str) -> bool

    # ---- 变更 (返回保存后状态) ----
    def enable(self, provider_id: str, **overrides) -> ProviderConfig
    def disable(self, provider_id: str) -> ProviderConfig
    def set_config(self, provider_id: str, **overrides) -> ProviderConfig

    # ---- key 解析 (禁明文日志) ----
    def resolve_api_key(self, provider_id: str) -> str
        # api_key_ref "env:VAR" → 进程 env → 项目 .env → 空;ollama 无 key 返回 ""
        # 任何 logger 只输出 ref 或 "configured=True/False",不输出 key 本体

    # ---- 装配决策 ----
    def any_enabled_with_key(self) -> bool        # 至少一个 enabled provider 且 key 可解析
    def selected_provider_id(self) -> str | None  # 第一个 enabled 且 key 可解析的 provider
    def select(self, task_type: str | None = None, required_capabilities: list[str] | None = None) -> ProviderSelection | None
        # 当前 v1: 返回第一个 enabled+key 可解析的 ProviderSelection (source="control-plane")
        # 未来 Router: 在此扩展 source/reason/score 字段,签名兼容 (task_type/capabilities 已预留)
    def resolve_runtime_config(self, provider_id: str) -> dict[str, Any] | None
        # ControlPlane → workflow_runner 装配契约: {provider, model, base_url, api_key, key_env, 费率}
        # model 取 models[0] (默认);不绑死 — workflow_runner 可显式传 model_id 覆盖
```

### 接线修改(workflow_runner.py,最小侵入)

```python
def has_llm_key() -> bool:
    # 现有:OPENAI_API_KEY env → get_llm() ...
    # 新增:LLMControlPlane().any_enabled_with_key() 参与判定 (D4 优先级)
    # ollama 本地无需 key → any_enabled 含 ollama 时也 True

def load_llm_key() -> str:
    # 现有逻辑保留;新增:providers.json 中 enabled provider 的 key 注入

def _build_provider(recorder) -> Any:
    # 现有:get_config().get_llm() 构建
    # 新增:LLMControlPlane.selected_provider_id() 优先 → 用该 provider 的
    #       model/base_url/费率;fallback 现有 get_llm() (兼容不破坏)
```

## 4. 修改范围

### 新增文件
1. `factory-console/llm_control.py` — LLMControlPlane(约 250-300 行)
2. `tests/llm/test_llm_control_persistence.py` — 持久化/加载/重启恢复/损坏容错
3. `tests/llm/test_llm_control_key.py` — api_key_ref 解析/env 引用/明文不落日志
4. `tests/llm/test_llm_control_runtime_binding.py` — has_llm_key/_build_provider 接线

### 修改文件
5. `factory-console/workflow_runner.py` — has_llm_key()/load_llm_key()/_build_provider() 三处接线(仅新增分支,不重写)

### 不动(用户禁止 + 冻结)
- factory-exec/exec/provider.py、providers/openai.py、providers/anthropic.py
- factory-exec/exec/agent_runtime.py、execution_loop.py、agent_executor.py
- factory-core/providers/(selector.py 保持零修改)
- factory-console/config.py(不改——ControlPlane 独立解析 env ref,workflow_runner 桥接)

## 5. 验收标准映射

| 验收 | 验证方式 |
|---|---|
| A. 重启后 Provider 配置仍存在 | test:save() → 新实例 reload() → 配置一致;真实验证:落盘后 cat providers.json |
| B. has_llm_key() 正确判断 | test:空配置 → False;配置 enabled+key_ref(env 注入)→ True;enabled 无 key → False;ollama → True |
| C. Provider 被 Runtime 真实装配 | test:_build_provider() 返回 OpenAIProvider 实例且 model/base_url 来自 providers.json;并冒烟 service._self_assemble_runtime() 非 None(注入测试 env) |
| D. 新增测试覆盖配置持久化和加载 | tests/llm/ 3 文件全绿 + 全量回归 pytest 不破坏现有 7775 |

## 6. 测试计划

1. **test_llm_control_persistence.py**(~10 cases)
   - save → load 往返一致
   - 新实例(重启模拟)reload 读回
   - 缺失文件 → 空配置不抛
   - 损坏 JSON → 响亮错误不静默
   - enable/disable 后 save 持久化
2. **test_llm_control_key.py**(~8 cases)
   - env:VAR 解析(environ 注入)
   - .env 兜底解析
   - 无 key → 空串
   - ollama 无需 key
   - logger 输出无 key 本体(caplog 断言)
3. **test_llm_control_runtime_binding.py**(~8 cases)
   - 空配置 → has_llm_key() False
   - 配置 deepseek enabled + key → True
   - selected_provider_id 返回正确 id
   - _build_provider 用 providers.json 的 model/base_url
   - 兼容:无 providers.json 时走 get_llm() 旧路径(回归保护)

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| workflow_runner 改动破坏现有 7775 | 只加分支不重写;全量 pytest 回归门 |
| providers.json 与 config.json/env 优先级歧义 | D4 显式优先级 + 测试锁定 |
| key 泄露日志 | caplog 断言 + 代码审查(所有 f-string 不含 key) |
| ollama 无 key 语义破坏 has_llm_key | 显式分支:enabled 含 ollama → True(本地无需 key) |

## 8. 实施顺序

1. llm_control.py 实现 + 2 个测试文件(纯新增,无破坏风险)
2. workflow_runner.py 三处接线 + runtime_binding 测试
3. 全量 pytest 回归(7775 + 新增 ~26)
4. 冒烟:写 providers.json → 重启 → 验证持久化 + has_llm_key
5. commit + push + completion 报告

---

> 设计 Review 完毕 | 待确认后开始实现
