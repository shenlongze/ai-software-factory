# ADR-0023 — Phase 8B-1: Provider 选择 + 执行集成 (Provider 接入 Execution 流程)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 8A (ADR-0022) 引入了 LLM Provider 扩展模型 (providers/ 六件套 +
`provider.*` 事件 + CLI provider 子命令), 但 Provider 只经 `provider test`
冒烟调用, **未接入编排**: Execution 流程 (ADR-0007) 完全不知道 Provider 存在。

Phase 8B-1 把 Provider 真正接入 Execution: 新增 **ProviderSelector** (四层
优先级选择链, 纯决策引擎) + **ProviderCarrierAdapter** (执行上下文载波,
Executor 注入模式) + CLI `execution run --provider <id>` + `workflow run
--auto` 的载波传递。冻结约束: **不实现 OpenAI/Claude Adapter** (只选择 +
审计, 不真调用智能来源); **Core 零修改** (execution/workflows/runtime/
runtimes/orchestration + events store/logger/metrics); **Removal Isolation
维持** (删除 providers 不影响 Factory)。

本 ADR 记录: 四层选择链语义、选择结果经 input dict 携带、载波注入模式、
Removal Isolation 的对称兜底、前置校验异常 catch 元组陷阱, 以及收尾
1 个失败测试的契约裁定 (2617 + 1 failed → 2618 全绿)。

## 决策

### 1. ProviderSelector: 四层优先级选择链 (纯决策, 无硬编码)

`providers/selector.py` — 选择优先级 (phase8-plan §Q5 / phase8b1-status.md):

```
explicit (CLI --provider) > project (project.yaml runtime_preferences.<task_type>.provider)
  > agent (角色级偏好) > runtime (Runtime 目录定义 metadata.default_provider)
  > default (ProviderRegistry.default)
```

- **配置层** (project/agent/runtime/default): 条目缺失 / 空 id / 未注册 /
  DISABLED → 该层视为缺失 → **降级下一层**; 全部缺失 → None (调用方走旧链路)。
  DISABLED 过滤依据: models.py `ProviderStatus` docstring "DISABLED 不参与
  选择/执行"。
- **显式层** (explicit): 用户明确指定 — 未注册/禁用 → **抛
  `ProviderNotFoundError`, 不静默降级** (用户意图须显式暴露; CLI 层转
  CliError rc 7, 同 cmd_provider_test 契约)。
- **注册表装配可选**: `ProviderSelector(registry)` 时配置层做存在性/状态
  校验 (`get(id)` None 或非 ACTIVE → 该层缺失); 不装配注册表 = 纯 id 链
  (provider=None, 无存储单测友好)。
- 结果 = `ProviderSelection` (frozen dataclass: provider_id/provider/source),
  source 取值 `SELECTION_SOURCES = ("explicit", "project", "agent", "runtime",
  "default")` — 即 provider.selected 事件 payload 的 source 字段。
- Agent 层: Agent 模型无 runtime_preferences 字段 → CLI 层恒传 None
  (角色级偏好留待未来), 选择链自动降级。
- runtime 层数据源: Runtime 目录定义 (`RuntimeCatalog.get`) 的
  metadata.default_provider / 顶层 provider 属性 (getattr 宽容读取,
  Runtime 模型零修改 — Core 边界)。
- 边界: 选择只产出 id + 来源; 是否真调用 Provider 由上层决定 — 本阶段仅
  选择 + 审计 (provider.selected), 不实现 OpenAI/Claude Adapter。

### 2. 选择结果经 ExecutionRequest.input dict 携带 (Core 零修改)

- 位置: CLI 层 `_resolve_execution_provider` (cli/commands.py), 在
  `service.run()` **之前**: `request.model_copy(update={"input": {**request.input,
  "provider_id": pid}})` + `store.save_execution(request)` 落盘 → runner 从
  store 重读 → adapter 可见。
- **仅 PENDING 请求携带**: 非 PENDING 由 runner 拒执行 (rc 1), 不改写已落盘
  请求 (input 原样)。
- 兼容依据: input 是 dict, 调用方构造; HermesRuntimeAdapter 忽略未知键,
  天然兼容 — 模型零改动。
- 无选择 → None → 不触碰请求 (input 零注入)。

### 3. ProviderCarrierAdapter 载波 = Executor 注入模式 (Phase 6E 复用)

`providers/integration.py` — 不复制执行逻辑, 只做"上下文传递 + 审计":

- `ProviderContext` (frozen dataclass: provider_id/model/source) = 装配点
  传递的已完成选择; `provider_context_from_selection(selection)` 转换
  (model 取定义首个模型)。
- `ProviderCarrierAdapter(delegate, context, logger)` 包装真实
  RuntimeAdapter; `execute()` 流程: `carry_provider_input` (注入
  input.provider_id) → **provider.selected** (payload execution_id/source)
  → provider.execution.started → delegate.execute → completed|failed
  (execution_id)。委托异常 → provider.execution.failed 后**原样抛出**
  (Runner 防御兜底转 FAILED, 不吞异常)。
- `wrap_adapters_with_provider(BUILTIN_ADAPTERS, context, logger)` 批量
  包装全部内置 Adapter, 返回**新 dict** (不改传入映射)。
- 装配点 (CLI):
  - `_open_execution_service(provider_context=...)`: 非 None → adapters =
    载波映射; None → 原装配 (旧链路逐位不变)。
  - `_cmd_workflow_run_auto`: `run_orchestration(..., adapters=载波映射 if
    context else None)` — orchestration/ 零修改 (Phase 6E executor 注入
    模式复用)。
- 事件序 (每次执行): execution.started (runner) → provider.selected →
  provider.execution.started → completed|failed → execution.completed|failed。
  **provider.selected 统一由载波在派发点发** (execution_id 恒可得) — CLI 与
  --auto 双路径一致, 无双发风险。source="cli"; usage 无真实计量时不传
  (payload 省略键, 同 Phase 8A 契约)。
- 无 provider 选择 → adapters=None → 旧链路: 零 provider 事件、input 零注入。

### 4. Removal Isolation 升级: 兜底必须对称覆盖"装配点消费函数"

- 选择辅助 `_resolve_provider_selection` 开头 `try: from providers...
  except ImportError: return None` — 无 providers 层 → 等同无配置 (旧链路),
  CLI 不崩; 所有 providers 导入保持延迟。
- **★ 收尾实测发现的实现缺口**: 选择辅助有 ImportError→None 兜底 ≠ 整条
  链路有兜底 — `workflow run --auto` 对选择结果**无条件**调
  `_provider_context_from_selection(selection)` (装配点消费函数), 该函数
  自身的延迟导入若裸写, 无 providers 层时 ImportError 漏到 main 兜底
  rc 1 (违反"删除 = 旧链路"契约)。修法: 装配点同样
  `try/except ImportError → return None` (与选择辅助对称); 修复后 --auto /
  execution run 在无 providers 层时都走旧链路 rc 0。
- 验证手段: monkeypatch `builtins.__import__` 对 `providers`/`providers.*`
  抛 ImportError (IMPORT_NAME 无条件调 __import__, 模块已在 sys.modules
  也被拦截 — 比删 sys.modules 条目干净, 无需恢复), 断言 rc 0 + 零
  provider.* 事件。
- **通用规律: 审计所有消费选择结果的延迟导入函数, 别只修选择入口。**

### 5. ★ 前置校验异常必须进 catch 元组 (rc7 裁定)

Phase 8B-1 实测 1 失败: `_resolve_execution_provider` 在 `service.run()`
**前**抛 `ExecutionNotFoundError` (执行不存在, cmd docstring 契约 rc 7),
但 cmd_execution_run 原 except 元组只有
`(ExecutionRunnerError, ExecutionDispatcherError, RuntimeNotFoundError)` →
异常漏到 main 兜底 `except Exception` → rc 1 (错)。

修法 (按继承关系二选一): 前置新异常若是既有 catch 元组内异常的**子类**
(实测: ExecutionNotFoundError ⊂ ExecutionRunnerError) → 把前置调用**移进
既有 try 块**即可命中 except, 元组零改动、单文件 diff (本会话实测路径);
非子类 → 显式加入 catch 元组或经 `_exec_cli_error` 映射。

仲裁: cmd docstring 的退出码契约 — 未找到 → 7 / --provider 未注册 → 7 /
状态冲突 → 1。这是**实现错**, 不是测试期望错。

通用规律: **给既有 try/except 命令插入前置逻辑时, 前置新抛的异常类型必须
同步进 catch 元组/错误映射 (或把调用移入 try 块), 否则静默降级到 rc 1**。

### 6. 收尾修复: test_auto_without_config_unchanged 契约裁定 (2617+1 → 2618)

- **失败**: `tests/providers/test_provider_cli_8b1.py::test_auto_without_config_unchanged`
  期望最后事件 `types[-1] == "workflow.completed"`, 实际
  `"orchestration.completed"`。
- **裁定: 测试期望错, 修测试不修实现** — `workflow run --auto` 走
  orchestration pipeline (`_cmd_workflow_run_auto` → `run_orchestration`),
  orchestration.completed 是既有正确行为 (ADR-0010 orchestration 层事件
  契约, 本阶段 orchestration/ 零修改)。该测试核心断言
  `"provider.selected" not in types` (provider 集成零侵入) **已通过** —
  只有终态事件名断言过期。修测试为 `orchestration.completed` + 注释说明
  --auto 路径, 实现零改动。
- 判定依据 = 同仓代码设计 docstring/契约 (cmd docstring 明示 --auto 经
  orchestration pipeline): 与既有先例 (ADR-0022 收尾三例) 一致。

## 影响

- 新增: `factory-core/providers/selector.py` (ProviderSelector +
  ProviderSelection + SELECTION_SOURCES), `factory-core/providers/integration.py`
  (ProviderContext / ProviderCarrierAdapter / carry_provider_input /
  wrap_adapters_with_provider / provider_context_from_selection);
  providers/config.py 增强 (parse_runtime_preferences 双键 /
  runtime_default_provider 宽容读取), providers/events.py 增强
  (provider.* 事件 payload 增 execution_id/source, 可选增量 kwargs,
  Phase 8A 载荷契约零破坏)。
- 修改: `factory-core/cli/main.py` (execution run --provider),
  `factory-core/cli/commands.py` (选择/装配/载波注入/ImportError 兜底)。
- 零改动: Core (execution/workflows/runtime/runtimes/orchestration);
  events store/logger/metrics; Dashboard。
- 测试: tests/providers/ (selector/config/events/integration/CLI/orchestration/
  removal isolation, 唯一 basename test_provider_*); 全量 **2618 绿**
  (Phase 8B-1 收尾)。
- 冒烟验证: 项目配置 provider → execution run → provider.selected 事件
  (source=project, payload 含 execution_id); 无配置 → 旧链路 (零 provider
  事件、input 零注入)。
