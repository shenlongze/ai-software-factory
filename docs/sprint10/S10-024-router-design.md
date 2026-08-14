# S10-024 LLM Router v1 — Design Review

> 日期:2026-08-13 | 状态:待确认 | 前置:S10-024-router-reality-check.md ✅
> 目标:统一 LLM 决策入口(User Explicit > Project Rule > System Recommendation > Fallback)
> 战略:为最终智能学习 Router 建立确定性决策基础(非学习,规则链)

---

## 1. 设计决策摘要

| # | 决策 | 理由 |
|---|---|---|
| D1 | 新增独立模块 `factory-console/llm_router.py` | 职责单一;不扩展 llm_control.select()(用户明确) |
| D2 | 优先级固定:User Explicit > Project Rule > System Recommendation > Fallback | 用户要求;确定性规则链,不学习 |
| D3 | Router 输出复用 ModelChoice {model_id, provider_id, score, reasons, source} | 用户要求;S10-022 已预留此结构,零新模型 |
| D4 | 接线点:workflow_runner._resolve_llm_config() 改调 Router | 路径 A+B 共同选择点,一处改全链生效 |
| D5 | Project Rule v1:project.yaml {llm: {routing: {default, task_types}}} | 用户要求;简单文件规则,无 DB |
| D6 | 新增审计事件 router.decided(events.db) | 决策可追溯;供未来学习 Router 数据基础 |
| D7 | Fallback = ControlPlane.selected_provider_id()(现状逻辑) | 行为兼容:无任何配置时与 S10-021/023 完全一致 |

## 2. Router 决策链(v1 确定性规则)

```
Router.route(task_type, context) → ModelChoice | None
│
├─ L1 User Explicit (用户指定)
│   context.explicit_provider / context.explicit_model
│   (来自: CLI --provider / 任务上下文 provider_id / API 参数)
│   → 校验存在+enabled → 命中即返回 (source="user-explicit")
│
├─ L2 Project Rule (项目规则)
│   project.yaml (project 根目录) → llm.routing
│   ├─ default: 该项目的默认 provider/model
│   └─ task_types: {task_type: provider/model} 按任务类型覆盖
│   → 校验存在+enabled → 命中即返回 (source="project-rule")
│
├─ L3 System Recommendation (系统推荐)
│   ModelCatalog.suggest(required_capabilities, provider_id?)
│   → 取第一个候选 (score/reasons 保留) (source="system-recommendation")
│
└─ L4 Fallback (默认)
    ControlPlane.selected_provider_id() + resolve_runtime_config
    → 与 S10-021 现状完全一致 (source="fallback")
```

### project.yaml 格式(v1)

```yaml
# <project_dir>/project.yaml — 项目级 LLM 路由规则 (可选文件)
llm:
  routing:
    default:
      provider: deepseek
      model: deepseek-chat
    task_types:
      code-review:
        provider: anthropic
        model: claude-sonnet-4
      data-analysis:
        provider: deepseek
        model: deepseek-reasoner
```

> 文件缺失 → 跳过 L2(降级 L3)。文件损坏/字段非法 → 响亮 warning + 跳过 L2(失败安全)。

## 3. 数据模型(llm_router.py, pydantic)

```python
class RouterRule(BaseModel):
    provider: str
    model: str | None = None          # None → ControlPlane 取该 provider 默认模型

class ProjectRoutingRules(BaseModel):
    default: RouterRule | None = None
    task_types: dict[str, RouterRule] = Field(default_factory=dict)

class ProjectLlmConfig(BaseModel):
    routing: ProjectRoutingRules = Field(default_factory=ProjectRoutingRules)
```

## 4. 接口设计(llm_router.py)

```python
class LLMRouter:
    """统一 LLM 决策入口: User Explicit > Project Rule > System Recommendation > Fallback。"""

    def __init__(self, control_plane: LLMControlPlane | None = None,
                 model_catalog: ModelCatalog | None = None,
                 event_logger: Any = None): ...   # 依赖可注入(测试隔离)

    def route(self, *, task_type: str | None = None,
              required_capabilities: list[str] | None = None,
              project_dir: str | Path | None = None,
              explicit_provider: str | None = None,
              explicit_model: str | None = None) -> ModelChoice | None:
        """四层决策链 → ModelChoice (source 标识命中层)。"""

    # ---- 各层实现 (可独立测试) ----
    def _layer_user_explicit(...) -> ModelChoice | None      # L1
    def _layer_project_rule(...) -> ModelChoice | None       # L2
    def _layer_system_recommendation(...) -> ModelChoice | None  # L3
    def _layer_fallback(...) -> ModelChoice | None           # L4

    # ---- project.yaml 读取 ----
    def load_project_rules(self, project_dir: str | Path) -> ProjectLlmConfig | None
        # 缺失 → None; 损坏 → warning + None (失败安全)

    # ---- 决策审计 ----
    def _emit_decided(self, choice: ModelChoice, task_type: str | None) -> None
        # router.decided 事件: {provider_id, model_id, source, reason, score}
```

### Router 输出的 ModelChoice 约定

```python
ModelChoice(
    model_id=...,           # L1/L2/L4 来自 ControlPlane resolve_runtime_config 的 model
    provider_id=...,        # 命中的 provider
    score=None,             # L3 来自 suggest; L1/L2/L4 为 None
    reasons=["layer: user-explicit", "reason detail..."],  # 命中层 + 理由
    source="user-explicit" | "project-rule" | "system-recommendation" | "fallback",
)
```

## 5. 接线修改(workflow_runner.py, 最小侵入)

```python
def _resolve_llm_config() -> dict[str, Any]:
    # S10-024: 改调 LLMRouter.route() 替换直接 ControlPlane.selected_provider_id()
    # 返回 {provider, model, base_url, api_key, key_env, 费率} (同 resolve_runtime_config 契约)
    # 未命中/异常 → get_config().get_llm() (legacy, 行为兼容)
```

具体:
1. `_resolve_llm_config()` 内:构造 LLMRouter(control_plane, model_catalog, event_logger)→ route()
2. 若 route() 返回 ModelChoice → 用 provider_id 调 ControlPlane.resolve_runtime_config()
3. 无 → get_config().get_llm()(与现状一致)

### Router 构造的 event_logger 来源
- workflow_runner 路径:start_project_workflow 有 events_db_path → 构造 EventLogger
- service 自装配路径:已注入 event_logger
- 无 logger → router.decided 静默(失败安全,不影响决策)

## 6. 修改范围

### 新增文件
1. `factory-console/llm_router.py`(~250 行)
2. `tests/llm/test_llm_router_priority.py`(~15 cases)— 四层优先级/降级链/输出字段
3. `tests/llm/test_llm_router_project_rules.py`(~12 cases)— project.yaml 读取/缺省/损坏
4. `tests/llm/test_llm_router_binding.py`(~10 cases)— workflow_runner 接线/fallback 兼容

### 修改文件
5. `factory-console/workflow_runner.py` — `_resolve_llm_config()` 一处改调 Router(~15 行)

### 运行时数据(不落 git)
6. `project.yaml`(各项目可选)— 由用户/项目自行创建

### 不动
- factory-console/llm_control.py、model_catalog.py、config.py、service.py
- factory-exec/exec/ 全部(agent_runtime/execution_loop/agent_executor/provider)
- factory-core/providers/ 全部(selector.py 冻结)
- 不实现:动态权重/历史学习/Memory/Multi Agent

## 7. 验收标准映射

| 验收 | 验证方式 |
|---|---|
| A. 四层优先级正确 | 测试:L1 命中不再查 L2/L3;L1 缺失 → L2;...;全缺 → L4 |
| B. 输出复用 ModelChoice | 测试:route() 返回 ModelChoice{model_id, provider_id, score, reasons, source} |
| C. project.yaml 规则生效 | 测试:配置 default/task_types → L2 命中;缺失 → 降级 |
| D. 接线生效 | 测试:workflow_runner._resolve_llm_config() 返回 Router 决策结果 |
| E. fallback 兼容 | 测试:无任何配置时行为与 S10-021 一致(返回 ControlPlane 第一个 enabled) |
| F. 审计事件 router.decided | 测试:route() 后事件落库 {provider_id, model_id, source, reason, score} |
| G. 全量回归 | pytest 不破坏基线(7888 + 2 预存失败) |
| H. commit + push | 提交成功 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 接线破坏现有执行链 | _resolve_llm_config() 只加 Router 分支;未命中回退 get_llm();全量回归门 |
| project.yaml 损坏拖垮 | 失败安全:损坏 → warning + 跳过 L2 |
| Router 与 factory-core selector 职责重叠 | 参考其模式不修改;Router 是 model 级决策(provider+model 两级),selector 是 provider 级目录查询 |
| 决策审计失败 | router.decided 事件失败安全(无 logger → 静默,决策不受影响) |
| ModelChoice 语义混淆(score=None) | source 字段区分:系统推荐 score 有值,规则链 score=None;reasons 说明 |

## 9. 实施顺序

1. llm_router.py + 3 测试文件(纯新增)
2. workflow_runner._resolve_llm_config() 接线
3. 定向测试绿 → 全量回归
4. 冒烟:无 project.yaml → fallback(与现状一致);配 project.yaml → 规则生效
5. commit + push + completion 报告

---

> Design Review 完毕 | 待确认后开始实现
