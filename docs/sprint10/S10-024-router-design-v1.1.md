# S10-024 LLM Router v1.1 — Design Review

> 日期:2026-08-13 | 状态:✅ 已确认 (v1.1 实现任务已下达) | 前置:S10-024-router-reality-check.md ✅ + S10-024-router-design.md(v1 被修订)
> 修订原因:Router v1 缺 Agent/Skill 级模型策略;AI Factory 定位是"管理 AI 员工+技能+生产流程",Agent/Skill 是核心对象,LLM 路由必须支持角色差异化
> 目标:五层决策链(L1 User Explicit > L2 Agent/Skill Policy > L3 Project Rule > L4 System Recommendation > L5 Fallback)
> 实现任务补充:新增独立模块 agent_policy.py(读取 ~/.factory/agents/<agent_id>/agent.yaml + skills/<skill_id>/skill.yaml),llm_router.py 只做决策链

---

## 1. Router 最终定位

**Router 是 AI Factory 的 LLM 决策中枢。**

输入:task / task_type / agent / skill / project / user constraints
输出:ModelChoice {model_id, provider_id, score, reasons, source}

Router 不负责:Provider 管理 / API Key / HTTP 调用 / Runtime 生命周期
(这些由 ControlPlane/Provider Adapter 承担——S10-021/023 已建立,Router 只做决策)

## 2. 五层决策优先级

```
L1 User Explicit          最高优先级 — 用户直接指定
L2 Agent/Skill Policy     角色策略 — agent.yaml / skill.yaml (新增)
L3 Project Rule           项目规则 — project.yaml
L4 System Recommendation  系统推荐 — ModelCatalog.suggest()
L5 Fallback               默认 — ControlPlane.selected_provider_id()
```

每层:命中(存在+enabled+key 可解析)→ 返回 ModelChoice;未命中/无 key → 降级下一层。
L1 显式指定若 provider 不存在/禁用 → 响亮错误(不静默降级,用户意图优先)。

## 3. Agent/Skill Policy 数据模型(新增层)

### agent.yaml(按 agent 目录,如 agents/backend-agent/agent.yaml)

```yaml
name: backend-agent

llm:
  routing:
    preferred:
      model: deepseek-chat
      provider: deepseek        # 可选;缺省取 ControlPlane 默认

    fallback:                    # 备选链 (preferred 不可用 → 依次尝试)
      - model: deepseek-reasoner
        provider: deepseek
      - model: qwen2.5-14b
        provider: ollama
```

### skill.yaml(按 skill 目录,如 skills/backend.development/skill.yaml)

```yaml
id: backend.development

llm:
  routing:
    preferred:
      model: deepseek-reasoner   # 复杂开发任务偏好推理模型

    fallback:
      - model: deepseek-chat
        provider: deepseek
```

### 决策语义(L2 内部)

```
L2 输入: agent_id / skill_ids (Agent 关联的技能列表)
优先级: Skill Policy > Agent Policy? 还是 Agent Policy > Skill Policy?
```

**设计决定:Agent Policy 优先于 Skill Policy**(Agent 是执行主体,Skill 是其能力组合;
Agent 级策略是总偏好,Skill 级策略在 Agent 无偏好时生效)。

```
L2 决策:
  1. agent.yaml 存在且 llm.routing.preferred 可解析 → 用它
  2. 否则遍历 agent 的 skills[], 第一个 skill.yaml 有 preferred 可解析 → 用它
  3. preferred 不可用(key 缺失/禁用) → 按 fallback 列表依次尝试
  4. 全部未命中 → 降级 L3
```

## 4. 数据模型(llm_router.py, pydantic)

```python
class RouterRule(BaseModel):
    provider: str
    model: str | None = None          # None → ControlPlane 取该 provider 默认模型

class AgentRoutingPolicy(BaseModel):  # agent.yaml 的 llm.routing
    preferred: RouterRule | None = None
    fallback: list[RouterRule] = Field(default_factory=list)

class SkillRoutingPolicy(BaseModel):  # skill.yaml 的 llm.routing (同构)
    preferred: RouterRule | None = None
    fallback: list[RouterRule] = Field(default_factory=list)

class ProjectRoutingRules(BaseModel):  # project.yaml 的 llm.routing
    default: RouterRule | None = None
    task_types: dict[str, RouterRule] = Field(default_factory=dict)
```

## 5. 接口设计(llm_router.py)

```python
class LLMRouter:
    """统一 LLM 决策入口: L1 User > L2 Agent/Skill > L3 Project > L4 System > L5 Fallback。"""

    def __init__(self, control_plane: LLMControlPlane | None = None,
                 model_catalog: ModelCatalog | None = None,
                 agent_store: Any = None,          # 可选: agent 查询 (factory-core AgentStore duck-typed)
                 skill_registry: Any = None,       # 可选: skill 查询 (exec SkillRegistry duck-typed)
                 event_logger: Any = None,
                 agents_dir: str | Path | None = None,   # agent.yaml 根 (默认 ~/.factory/agents)
                 skills_dir: str | Path | None = None,   # skill.yaml 根 (默认 ~/.factory/skills)
                 projects_dir: str | Path | None = None): ...  # project.yaml 根

    def route(self, *, task_type: str | None = None,
              required_capabilities: list[str] | None = None,
              agent_id: str | None = None,
              skill_ids: list[str] | None = None,
              project_dir: str | Path | None = None,
              explicit_provider: str | None = None,
              explicit_model: str | None = None) -> ModelChoice | None:
        """五层决策链 → ModelChoice (source 标识命中层)。"""

    # ---- 各层 (独立可测) ----
    def _layer_user_explicit(...) -> ModelChoice | None            # L1
    def _layer_agent_skill_policy(...) -> ModelChoice | None       # L2
    def _layer_project_rule(...) -> ModelChoice | None             # L3
    def _layer_system_recommendation(...) -> ModelChoice | None    # L4
    def _layer_fallback(...) -> ModelChoice | None                 # L5

    # ---- 配置读取 (失败安全) ----
    def load_agent_policy(self, agent_id: str) -> AgentRoutingPolicy | None
    def load_skill_policy(self, skill_id: str) -> SkillRoutingPolicy | None
    def load_project_rules(self, project_dir: str | Path) -> ProjectLlmConfig | None

    # ---- 决策审计 ----
    def _emit_decided(self, choice: ModelChoice, task_type: str | None) -> None
        # router.decided 事件: {provider_id, model_id, source, reason, score}
```

### 配置路径约定

```
agent.yaml:  <agents_dir>/<agent_id>/agent.yaml   (~/.factory/agents/backend-1/agent.yaml)
skill.yaml:  <skills_dir>/<skill_id>/skill.yaml   (~/.factory/skills/backend.development/skill.yaml)
project.yaml: <project_dir>/project.yaml          (沙箱项目根, 与 S10-024 v1 一致)
```

> 均为可选文件;缺失 → 跳过该层(降级)。损坏/非法 → warning + 跳过(失败安全)。

## 6. 接线修改(workflow_runner.py, 最小侵入)

```python
def _resolve_llm_config() -> dict[str, Any]:
    # S10-024 v1.1: 改调 LLMRouter.route() (五层链) 替换直接 ControlPlane.selected_provider_id()
    # Router 输入来自: task (agent_id/skill_ids/type), context (project_dir/explicit)
    # 返回 {provider, model, base_url, api_key, key_env, 费率} (同 resolve_runtime_config 契约)
    # 未命中/异常 → get_config().get_llm() (legacy, 行为兼容)
```

**接线输入来源**(AgentExecutor 执行链):
- agent_id:AgentExecutor.execute_task 已有参数
- task_type:task.type / context
- project_dir:context.project_dir(已有)
- skill_ids:Agent.skills(agent_store 查询)或 context
- explicit:context.explicit_provider / explicit_model

## 7. 修改范围

### 新增文件
1. `factory-console/llm_router.py`(~350 行,五层 + 配置读取)
2. `tests/llm/test_llm_router_priority.py`(~18 cases)— 五层优先级/降级链/L1 响亮错误
3. `tests/llm/test_llm_router_agent_skill.py`(~15 cases)— agent.yaml/skill.yaml 读取/Agent>Skill 优先级/fallback 链
4. `tests/llm/test_llm_router_project.py`(~12 cases)— project.yaml 读取/缺省/损坏
5. `tests/llm/test_llm_router_binding.py`(~10 cases)— workflow_runner 接线/fallback 兼容

### 修改文件
6. `factory-console/workflow_runner.py` — `_resolve_llm_config()` 改调 Router(~15 行)

### 运行时数据(不落 git)
7. `~/.factory/agents/<id>/agent.yaml`(可选)、`~/.factory/skills/<id>/skill.yaml`(可选)、`project.yaml`(可选)

### 不动
- factory-console/llm_control.py、model_catalog.py、config.py、service.py
- factory-exec/exec/ 全部
- factory-core/providers/ 全部(selector.py 冻结)
- 不实现:动态权重/历史学习/Memory/Multi Agent

## 8. 验收标准映射

| 验收 | 验证方式 |
|---|---|
| A. 五层优先级正确 | 测试:L1 命中不再查下层;L1 缺 → L2;...;全缺 → L5 |
| B. Agent/Skill 策略生效 | 测试:agent.yaml preferred 命中;Agent>Skill 优先;fallback 链依次尝试 |
| C. project.yaml 规则生效 | 测试:default/task_types → L3 命中 |
| D. 输出复用 ModelChoice | 测试:route() 返回 ModelChoice{model_id, provider_id, score, reasons, source} |
| E. 接线生效 | 测试:workflow_runner._resolve_llm_config() 返回 Router 决策结果 |
| F. fallback 兼容 | 测试:无任何配置时行为与 S10-021 一致(返回 ControlPlane 第一个 enabled) |
| G. 审计事件 router.decided | 测试:route() 后事件落库 {provider_id, model_id, source, reason, score} |
| H. 全量回归 | pytest 不破坏基线(7888 + 2 预存失败) |
| I. commit + push | 提交成功 |

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| Agent/Skill yaml 生态从零起步 | v1.1 只建读取机制+默认空;用户按需创建;不做迁移/导入 |
| Agent>Skill 优先级判断错误 | 设计明确定义(Agent 总偏好优先);测试锁定 |
| preferred 不可用(key 缺失) | fallback 列表依次尝试;全失败降级 L3 |
| 接线破坏现有执行链 | _resolve_llm_config() 只加 Router 分支;未命中回退 get_llm();全量回归门 |
| 配置读取失败拖垮 | 全部失败安全(缺失/损坏 → warning + 跳过该层) |
| Router 与 factory-core selector 职责重叠 | 参考模式不修改;Router 是 model 级决策(五层),selector 是 provider 级目录查询 |

## 10. 实施顺序

1. llm_router.py + 4 测试文件(纯新增)
2. workflow_runner._resolve_llm_config() 接线
3. 定向测试绿 → 全量回归
4. 冒烟:无配置 → L5 fallback(与现状一致);建 agent.yaml → L2 生效;配 project.yaml → L3
5. commit + push + completion 报告

---

> Design Review v1.1 完毕 | 待确认后开始实现
