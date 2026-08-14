# S10-024 LLM Router v1 — Reality Check

> 日期:2026-08-13 | 状态:只读取证,未修改代码 | 前置:S10-021 ✅ + S10-022 ✅ + S10-023 ✅
> 目标:统一 LLM 决策入口(用户指定 > 项目规则 > 系统推荐 > 默认 fallback),非智能学习 Router

---

## 1. 当前 LLM 选择路径(现状全览)

```
┌─ 路径 A: workflow 生产路径 (start_project_workflow) ─────────────────┐
│  workflow_runner._build_provider(recorder)                            │
│    → _resolve_llm_config()  [S10-021 接线]                            │
│      → LLMControlPlane.selected_provider_id()  ← 第一个 enabled+key   │
│      → resolve_runtime_config(pid) → {provider, model, base_url, key} │
│      → OpenAIProvider/AnthropicProvider → _RecordingProvider 包装     │
│    未命中 → get_config().get_llm() (legacy, S10-007)                  │
└──────────────────────────────────────────────────────────────────────┘

┌─ 路径 B: Agent 执行路径 (AgentExecutor.execute_task) ────────────────┐
│  service._self_assemble_runtime() → workflow_runner._build_provider    │
│  → AgentRuntime(provider) → AgentExecutionLoop                        │
│    → LLMPlanner(provider=runtime.developer.provider)  [execution_loop] │
│    → FINAL → runtime.execute → DeveloperAgent.work → provider.generate │
└──────────────────────────────────────────────────────────────────────┘

┌─ 路径 C: exec CLI (cmd_exec_run) ────────────────────────────────────┐
│  _provider_registry() [S10-023 修复]                                  │
│    → ControlPlane.selected_provider_id() > legacy default_registry()  │
└──────────────────────────────────────────────────────────────────────┘
```

**现状缺陷:选择逻辑 = "第一个 enabled+key 可解析的 provider"**(ControlPlane.selected_provider_id)。
没有"用户指定/项目规则/系统推荐"任何一层;ModelCatalog 完全未参与执行选择(suggest 只是独立查询,无调用方)。

## 2. ModelCatalog 接口(可复用)

| 接口 | 签名 | 状态 |
|---|---|---|
| suggest() | (required_capabilities, min_quality, max_cost_per_1k, min_context_window, provider_id) → list[ModelChoice] | ✅ 实现(S10-022) |
| ModelChoice | {model_id, provider_id, score, reasons[], source} | ✅ Router 兼容预留 |
| find_by_capability() | (capability, enabled_only) → list[ModelInfo] | ✅ |
| list_models() / get_model() | 基础查询 | ✅ |
| models_by_provider() | 两级结构查询 | ✅ |

**ModelChoice 已含 Router 所需字段(score/reasons/source),可直接作为 Router 输出。**

## 3. Execution 调用入口(接线点候选)

| 入口 | 位置 | 特征 |
|---|---|---|
| workflow_runner._build_provider() | workflow_runner.py:490 | **唯一真实 Provider 装配点**,路径 A/B 共用 |
| _resolve_llm_config() | workflow_runner.py:471 | 当前选择逻辑所在,Router 插此最合适 |
| AgentExecutionLoop._provider() | execution_loop.py:339 | runtime 装配后取 provider,只读 |
| AgentExecutor.execute_task() | agent_executor.py:122 | 编排入口,runtime 已装配 |

**Router 插入点分析:workflow_runner._resolve_llm_config() 是两条生产路径(A+B)的共同选择点,是 Router v1 的最佳挂载位置。** 路径 C(CLI)的 _provider_registry() 也调 ControlPlane,可复用同一 Router 接口。

## 4. Usage 数据结构(Router 反馈数据)

| 数据源 | 字段 | 说明 |
|---|---|---|
| ExecutionResult.usage(exec 路径) | prompt_tokens/completion_tokens/total_tokens/estimated_cost_usd | S10-023 真实记录 750/55/805/$0.000233 |
| Recorder.calls(workflow 路径) | model/max_tokens/usage/latency_s/ok/error/content_len/cost_usd_est | workflow_runner.py:389 |
| usage.json(factory-core) | provider_id/model/prompt_tokens/completion_tokens/estimated_cost/latency_ms/success/error | 只服务 hermes adapter,未统一 |

**Router v1 决策输入不依赖 Usage**(确定性规则链),但输出决策要记录(供未来学习 Router)。

## 5. Audit 数据结构(决策审计)

| 数据源 | 事件类型 | 字段 |
|---|---|---|
| events.db(org) | provider.selected(10 条已有) | payload 结构待查 |
| runtime-session | llm_request_sent / llm_response_received | provider_id/task_id; provider_id/status |
| ExecutionResult | 无独立决策字段 | — |

**Router v1 需要新增决策记录:router.decided 事件(provider_id/model_id/source/reason/score)或复用 provider.selected 扩展。**

## 6. 可复用能力清单

| 能力 | 来源 | 复用方式 |
|---|---|---|
| ControlPlane.select() → ProviderSelection | llm_control.py:312 | **已预留 Router 签名**(task_type/required_capabilities 参数在) |
| ModelCatalog.suggest() → list[ModelChoice] | model_catalog.py:295 | 系统推荐层直接调用 |
| factory-core ProviderSelector 四层链 | selector.py(冻结) | **参考其优先级模式,不修改**(explicit>project>agent>runtime>default) |
| ProviderSelection 字段 | llm_control.py:65 | source/reason/score 已在 |
| ModelChoice 字段 | model_catalog.py:76 | source/reason/score 已在 |
| 决策记录:provider.selected 事件 | events | 扩展或复用 |

## 7. Router v1 设计约束建议(Reality Check 结论)

```
用户指定 (explicit: CLI --provider / 任务上下文 provider_id)
  > 项目规则 (project rules: task 所属 project 的 provider/model 偏好)
  > 系统推荐 (system suggest: ModelCatalog.suggest 基于 capabilities)
  > 默认 fallback (ControlPlane.selected_provider_id / get_llm legacy)
```

### 关键设计问题(Design Review 待定)

1. **Router 放哪一层**:新增 factory-console/llm_router.py(独立模块,复用 ControlPlane+ModelCatalog)vs 扩展 llm_control.select()
2. **接线点**:workflow_runner._resolve_llm_config() 改为调 Router(一处改),还是保留现链+Router 只做上层决策
3. **"项目规则"数据源**:task 的 project 关联(backlog task.project / exec Task.project)是现有字段,但需定义规则文件格式(rules.json? 还是 task.context 透传?)
4. **决策记录**:新增 router.decided 审计事件(provider_id/model_id/source/reason/score)
5. **与 factory-core selector.py 关系**:其四层链骨架是 provider 级且冻结;Router v1 是 model 级决策(provider+model 两级),可参考不修改

### 明确不做(用户约束)

- 动态权重 / 历史学习 / 自动优化(Phase 5 暂缓)
- 修改 selector.py 核心逻辑
- Multi Agent / Memory / Learning Loop

## 8. 结论

- **Router 数据基础已齐**:ControlPlane(provider 配置)+ ModelCatalog(model 元数据)+ Real Execution(真实 usage)+ Audit(决策可记录)
- **最佳插入点**:workflow_runner._resolve_llm_config()(路径 A+B 共同选择点)
- **最大复用**:ControlPlane.select() 已预留 Router 签名;ModelCatalog.suggest() 已产出 ModelChoice(score/reasons/source)
- **主要缺口**:① 统一决策入口(现为"第一个 enabled")② 项目规则层数据源 ③ 决策审计记录

---

> Reality Check 完毕 | 未修改任何代码 | 待确认后 Design Review
