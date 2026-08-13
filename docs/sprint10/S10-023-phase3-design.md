# S10-023 Phase 3 设计 Review — LLM Real Execution Activation (Rev 2 — 用户确认版)

> 日期:2026-08-13 | 状态:✅ 已确认 (Rev 2) | 前置:S10-021 Control Plane ✅ (c1c535f) + S10-022 Model Catalog ✅ (81a2426)
> 范围:第一次真实 LLM 生产执行闭环(Task→Model→LLM→Artifact→Audit→Usage)
> 战略:为最终 Smart Router 提供真实执行数据基础(usage/cost/latency/result)
> Rev 2 变更:按用户 6 条额外约束确认 ——
> ① 真实执行必须走 ControlPlane 路径 (ControlPlane→Provider→Model), 禁止独立 Provider 配置体系
> ② exec CLI 装配优先级 ControlPlane > legacy registry > fallback, 不形成第二套配置
> ③ 真实冒烟允许 DEEPSEEK key: key 不落盘 / 日志不输出 key / 费用极小范围
> ④ 执行记录尽量含 provider_id/model_id/tokens/latency/cost/status (供未来 Router)
> ⑤ 第一次真实执行用简单可验证任务 (证明完整链路, 非复杂能力)
> ⑥ 禁止: Router / selector 核心逻辑修改 / Multi Agent / Memory / Learning Loop

---

## 1. 现状(真实代码取证)

| 链路环节 | 状态 | 证据 |
|---|---|---|
| Task/Agent 数据 | ✅ 存在 | ~/.factory/tasks/ 有 T-001 等 5 个 task;org/projects.json 有 P-806fe6e8(ScorePocket)等 |
| AgentExecutor | ✅ 代码完整 | factory-exec/exec/agent_executor.py — Task→Session→Loop→LLM→Result 编排 |
| LLMPlanner | ✅ 代码完整 | execution_loop.py:164 — 复用 ProviderInterface.generate,无 key 诚实 FINAL |
| DeveloperAgent.work | ✅ 真实调用点 | developer.py:632 `response = self._provider.generate(...)` |
| usage 记录 | ✅ 代码完整 | agent_runtime.py:539/563 把 usage 带进 ExecutionResult;_RecordingProvider 记录 latency/cost |
| Audit 事件 | ✅ 代码完整 | org.execution.* 事件链(agent_runtime.py:597) |
| **真实 LLM 调用** | ❌ **从未发生** | usage.json 全是 hermes CLI 超时失败;无一次 OpenAI/DeepSeek 成功调用 |
| **providers.json** | ❌ 未配置 | ~/.factory/providers.json 不存在 |
| DEEPSEEK key | ✅ 可用 | ~/.hermes/.env 含 DEEPSEEK_API_KEY(Phase 1 确认 api_key_ref=env: 引用可用) |

## 2. 关键发现:两条 Provider 装配路径

```
路径 A (service/workflow 生产路径):  ✅ 已接 Phase 1 ControlPlane
  providers.json → LLMControlPlane → workflow_runner._build_provider
  → OpenAIProvider(deepseek 兼容端点) → AgentRuntime
  → service._self_assemble_runtime() 已接线 (service.py:389)

路径 B (exec CLI 路径):               ❌ 未接 ControlPlane
  exec/cli.py:_provider_registry() → default_registry()
  → 只注册 anthropic/openai (provider.py:126-146) → **deepseek 不可用**
  → cmd_exec_run 用此路径 (cli.py:141)
```

**结论:Phase 3 真实执行必须走路径 A**(service/AgentExecutor 生产装配),或修复路径 B 的装配。
路径 B 修复 = 让 exec CLI 的 `_provider_registry()` 优先从 ControlPlane 取(一处小改)。

## 3. 设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 验证入口用 **AgentExecutor.execute_task**(service 生产路径,走 ControlPlane) | 完整链 Task→Session→Planner→LLM→Result,且 provider 来自 Phase 1 配置 |
| D2 | 同时修复路径 B:exec CLI `_provider_registry()` 增加 ControlPlane 优先分支 | CLI 与 service 装配一致;用户任一入口都能真实执行 deepseek |
| D3 | 真实执行方式:后端 8011 启动(service 自装配)→ 配置 providers.json → 注入 key → execute_runtime_task API 调用 | 生产等价路径,非 mock、非临时脚本 |
| D4 | 记录:usage.json(provider.usage.recorded)+ org.execution.* 审计事件 + ExecutionResult.usage | 现有机制复用,零新持久化 |
| D5 | 冒烟任务:用现有 task(T-001)+ 现有 agent(backend-1)执行一次真实任务 | 复用已有数据,不造新数据;任务可换成最小验证目标 |
| D6 | 不实现:Router/动态权重/历史学习;不改 AgentRuntime/execution_loop 核心流程 | 用户约束;只做"激活"不做"增强" |

## 4. 修改范围

### 修改文件(1 个,最小)
1. `factory-exec/exec/cli.py` — `_provider_registry()` 增加 ControlPlane 优先分支(约 10 行):
   ```python
   def _provider_registry() -> ProviderRegistry:
       # S10-023: 优先从 ControlPlane 装配 (providers.json 的 enabled provider)
       try:
           from factory_console.llm_control import LLMControlPlane  # 延迟 import
           ...
           plane = LLMControlPlane()
           pid = plane.selected_provider_id()
           if pid is not None and pid in ("openai", "anthropic"):
               from .providers.openai import OpenAIProvider
               from .providers.anthropic import AnthropicProvider
               # 用 resolve_runtime_config 构建对应 Provider 实例
       except Exception:
           pass  # 失败安全 → 回退 default_registry()
       return default_registry()
   ```
   > ⚠️ 实现时注意:exec 包不能直接 import factory-console(包名带连字符,依赖 PYTHONPATH);需按项目既有模式处理。若装配复杂度高,退化为:CLI 增加 `--provider deepseek` 支持(从 ControlPlane 读 base_url/model/key)。

### 新增文件(2 个)
2. `tests/llm/test_real_execution_binding.py`(~10 cases)— 不调用真实 API,验证装配正确性:
   - _provider_registry() 在 providers.json 配置 deepseek 时能装配 OpenAIProvider(注入 ControlPlane)
   - ControlPlane → resolve_runtime_config → OpenAIProvider 构造参数正确(model/base_url 来自配置)
   - 失败安全:无 providers.json → 回退 default_registry()
3. `docs/sprint10/S10-023-real-execution-report.md`(执行后产出)— 真实执行证据报告(usage/cost/latency/result)

### 运行时配置(不提交 git)
4. `~/.factory/providers.json` — 配置 deepseek(enabled=true, api_key_ref=env:DEEPSEEK_API_KEY)
   - 由验证步骤创建(Phase 1 已支持;不落 git)

### 不动
- factory-exec/exec/agent_runtime.py、execution_loop.py、agent_executor.py、provider.py
- factory-console/llm_control.py、model_catalog.py、workflow_runner.py、config.py、service.py
- factory-core/providers/ 全部
- 不实现 Router/学习逻辑

## 5. 验收标准映射

| 验收 | 验证方式 |
|---|---|
| A. 真实 LLM 调用发生 | 后端启动 + execute_runtime_task 调用 → usage.json 出现成功记录(provider=deepseek, tokens>0) |
| B. 全链跑通 | Task→Session→Planner→LLM→Result→Audit;runtime-sessions 出现 status=success 的真实 session |
| C. 执行指标记录 | usage.json 记录 model_id/provider_id/tokens/cost/latency;ExecutionResult.usage 非空 |
| D. 审计可见 | org.execution.completed 事件落库(events.db) |
| E. 装配修复生效 | exec CLI _provider_registry() 能装配 deepseek(测试 + 冒烟) |
| F. 全量回归 | pytest 不破坏基线(7878 + 2 预存失败) |
| G. commit + push | 提交 cli.py 修改 + 测试 |

## 6. 真实执行冒烟步骤(验收时执行)

```
1. 写 ~/.factory/providers.json (deepseek enabled + api_key_ref=env:DEEPSEEK_API_KEY)
2. set -a; source ~/.hermes/.env; set +a   # key 注入进程环境(不落盘明文)
3. 启动后端 8011 (service 自装配 → ControlPlane → OpenAIProvider)
4. curl POST /api/runtime/execute (或 execute_runtime_task) 用 T-001 + backend-1
5. 验证:session success + usage.json 记录 + events 审计
6. 若 provider 装配失败 → 读错误事件诚实记录根因,修复后重试
```

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 真实调用失败(网络/key/端点) | 诚实记录失败事件;读 report/usage 根因;修复后重试(不动代码前先查装配) |
| exec CLI 装配修复复杂(包名连字符) | 退化为 CLI --provider deepseek 支持;或只验证路径 A(service),路径 B 记录为已知限制 |
| key 泄露 | 只在进程环境注入;providers.json 只存 env: 引用;日志不输出 key |
| 验证破坏用户环境(8011) | 验收后恢复用户环境服务(铁律:杀服务后必须恢复) |
| 测试挂起(真实 API 超时) | 测试全部走装配验证(不调 API);真实调用只在冒烟步骤手动执行 |

## 8. 实施顺序

1. cli.py 装配修复 + 装配测试(纯本地,无真实 API)
2. 全量回归(7878 基线确认)
3. 真实冒烟:配置 providers.json + 注入 key + 启动 8011 + execute_runtime_task
4. 收集证据 → 写 S10-023-real-execution-report.md
5. commit(cli.py + 测试 + 报告)+ push + report

---

> 设计 Review 完毕 | 待确认后开始实现
