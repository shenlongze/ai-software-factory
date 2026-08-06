# ADR-0022 — Phase 8A: LLM Provider Extension Model (Provider 扩展模型层)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 8A 给 Factory 加 **LLM Provider 层**: `factory-core/providers/` 六件套
(models/store/definitions/registry/provider/events) + `adapters/` 内置实现包
(hermes) + CLI `provider list/show/test` + Dashboard Provider View (第 17 视图) +
`provider.*` 审计事件。设计文档 phase8a-status.md 明令 **冻结约束**:
删除 providers 不影响 Factory (Removal Isolation), 0 修改 Core (runtime/ 等)。

Factory 此前只有"执行机制" (Runtime: runtime/*, ADR-0006/0009/0014) — 每个
Runtime 自带 execution adapter, 无独立的"智能来源"抽象。Phase 8A 引入 Provider
扩展模型: **Provider = 智能来源 (谁产生智能), Runtime = 执行机制 (谁执行动作)**,
两者数据空间、命名空间、生命周期完全分离, 并存不替换。

本 ADR 界定 Provider 扩展模型、Runtime-Provider 分离边界、Hermes 双角色、
配置优先级、独立生命周期, 并记录 Phase 8A 收尾 3 个失败测试的契约裁定
(2457 → 2460 全绿)。

## 决策

### 1. Provider Extension Model: Catalog (定义) + Registry (合并视图) + Adapter (实现) 三层

- **ProviderDefinition** (models.py) = 能力目录数据: id/name/type (cloud/local/
  agent)/capabilities/models/version/status (ACTIVE|DISABLED)/config_schema/
  metadata。只描述不执行; 不包含任何 OpenAI/Claude 专有结构。
- **ProviderStore** (store.py) = JSON 持久化 `<root>/providers/catalog.json`
  (双节: `definitions` + `default`), 原子写 (tmp + os.replace); 损坏报
  `CorruptProviderStoreError` 绝不静默返回空 (同 runtimes/store.py 模式)。
- **默认定义基线** (definitions.py) 常驻代码层: `DEFAULT_PROVIDER_DEFINITIONS`
  (hermes, builtin), 读路径由 ProviderRegistry 合并 — **默认 id 保留只读**
  (register 冲突抛 ProviderExistsError, remove 抛 ProviderRegistryError),
  永不自动落盘 (同 ADR-0014 决策 3 模式)。
- **ProviderRegistry** (registry.py) = 目录读路径 (合并视图 get/list/
  find_by_capability/count/ids) + 写路径 (register/remove 只作用持久化层,
  返回 `(对象, Event | None)`) + 默认选择 (set_default/default/resolve)。
- **ProviderAdapter** (provider.py) = 抽象接口 (ABC): `generate/chat/stream`
  统一 I/O 契约 (ProviderRequest/ProviderResponse, 失败返回 error 响应不抛
  异常 — 同 HermesRuntimeAdapter 失败处理哲学); 实现注册进
  `BUILTIN_PROVIDER_ADAPTERS` (adapters/__init__.py, 模块级单例)。
- **实现与目录解耦** (同 ADR-0007 决策 3 模式): 内置 Adapter 只提供"实现",
  能力声明由目录合并视图提供; 已注册但无内置实现的 Provider →
  CLI `provider test` 配置缺口 rc 1 (同 cmd_runtime_test 契约)。

### 2. Runtime-Provider 分离 (数据空间 / 命名空间 / 职责)

- **职责**: Runtime = 执行机制 (execution adapter 驱动 hermes CLI 跑任务,
  ADR-0009); Provider = 智能来源 (生成文本/对话/推理, Factory 默认 hermes)。
- **数据空间完全分离**: `providers/catalog.json` vs `runtimes/catalog.json` /
  `runtimes/runtimes.json` — ProviderRegistry 与 RuntimeRegistry 互不引用,
  禁止混合 (phase8a-status.md 冻结约束)。
- **命名空间独立**: Provider 命名空间 (hermes) 独立于 Runtime 命名空间
  (runtime 的 hermes 身份为 `hermes-runtime`) — 同 id 不同含义合法。
- **Removal Isolation**: CLI 命令层延迟导入 providers (`_open_provider_store` /
  `cmd_dashboard` 的 view == "provider" 分支), dashboard/collector 零顶层
  imports providers — 删除 providers 不影响 Factory 加载与其余命令。

### 3. Hermes 双角色 (并存不替换)

- **HermesRuntimeAdapter** (runtime/adapters/hermes.py, id=`hermes-runtime`):
  执行角色, **零改动** — Phase 4C (ADR-0009) 既有执行出口。
- **HermesProviderAdapter** (providers/adapters/hermes.py, id=`hermes`): 智能
  角色, 纯新增 — `hermes -z <prompt>` one-shot subprocess (同 ADR-0009 决策 1
  调用方案), 配置经环境变量覆盖 (FACTORY_PROVIDER_HERMES_CMD /
  FACTORY_PROVIDER_HERMES_TIMEOUT), 构造参数优先于环境变量。
- 职责边界: 执行编排 (execution 层) 继续走 Runtime; 智能生成 (未来
  workflow/agent 决策) 走 Provider。本阶段 Provider 只经 `provider test`
  冒烟调用, 不接入编排 (Phase 8c 接入)。

### 4. 配置优先级 (本阶段 default/resolve 基础, Phase 8c 完整实现)

- 选择优先级 (phase8-plan §Q5): **显式项目配置 > Agent 要求 > Runtime 能力 >
  Registry 默认** — 完整解析由 Phase 8c 实现。
- 本阶段 ProviderRegistry 提供基础: `set_default` 持久化默认 id
  (provider.selected stage=default); `default()` 返回默认定义 (默认引用已
  移除 → 自动失效返回 None, 不抛错); `resolve(provider_id=None)` = 显式 id
  (须已注册, 否则 ProviderNotFoundError) → 默认 → None (调用方自行兜底, 同
  resolve_runtime_id 语义)。
- config_schema (definitions.py) 描述配置项 (command/timeout_s/mode, 含 env
  绑定) — 只描述不包含密钥明文; 本阶段适配器直接读环境变量, API 模式预留。

### 5. 独立生命周期: 事件 + CLI + Dashboard

- **事件** (provider.*, EventType 枚举成员, ADR-0001 决策 1: 加成员即扩展):
  - 生命周期: `provider.registered` / `provider.removed` / `provider.viewed`
  - 执行: `provider.selected` → `provider.execution.started` →
    `provider.execution.completed` (result=OK) | `provider.execution.failed`
    (result=ERROR)
  - events.py 辅助函数封装 payload 契约 (logger 可缺省 → 返回 None); source
    约定: 注册表/服务层 `provider_registry`, CLI 读命令 `cli` (CLI 不依赖
    本模块 — Removal Isolation)。payload 契约与 Dashboard Provider View /
    CLI --json 出口一致。
- **CLI** (main.py `factory provider list/show/test`, ADR-0002: 所有 CLI 行为
  必须产生 Event):
  - `provider list` — 目录表 (合并视图 + default 标记), 发 provider.viewed;
    可 --type/--status 过滤。
  - `provider show <id>` — 定义详情, 发 provider.viewed; 未找到 rc 7。
  - `provider test <id>` — smoke: adapter.generate 最小调用 (默认提示词
    "Reply with exactly: OK"), 事件序 selected → execution.started →
    completed|failed → viewed; 退出码 0 SUCCESS / 1 FAILED 或配置缺口 /
    7 未找到; smoke 为临时调用 **不落任何 Provider 状态** (目录零残留)。
- **Dashboard Provider View** (第 17 视图): `ProviderSnapshot` (total/by_type/
  by_status/default/items) + `FactorySnapshot.providers` 默认空; collector
  `include_provider` 缺省关 (同 include_git/change/changeflow 模式, 零回归);
  CLI `dashboard --view provider` 按视图装配 `ProviderRegistry(<root>/providers)`
  (延迟导入); collector 不发事件 (provider.viewed 由 CLI 命令层发出, 同
  dashboard.viewed 边界)。VIEWS 精确集合断言随视图扩展数学上必然失败
  (16→17), 最小化更新 + 本 ADR 记录 (第六犯先例, 同 ADR-0014/0017/0018/0019/0020)。

### 6. find_by_capability 语义 (大小写不敏感精确匹配, 合并视图)

- 检索 = 大小写不敏感 **精确匹配** (不含子串): `capability='chat'` 不命中
  `chatty`; 空串/空白 → []。
- 检索范围 = **合并视图** (默认定义基线 + 已持久化定义, 同 get/list/count/
  ids) — 默认 hermes 基线 capabilities 含 `chat`, 故 `find("chat")` 命中
  hermes 是正确行为 (与"只搜持久化定义"的直觉不同, 见收尾裁定 8.2/8.3)。

### 7. 收尾修复: 3 个失败测试的契约裁定 (2457 → 2460)

1. **test_success_usage_metrics (测试期望错, 修测试)**: `output_chars` 语义 =
   `len(stdout)` 原始输出字符数 (含换行) — models.py 定义 usage 为"可移植计量
   dict", 未定义"排除尾部换行"语义; `len("ab\ncd\n")` = 6, 原断言 5 为手数
   错误 (漏尾部 \n)。修测试为 6, 实现零改动。
2. **test_find_by_capability_exact_ci (测试期望错, 修测试)**: 合并视图含默认
   hermes 基线 (capabilities 含 `chat`), `find("chat")` 返回
   `["claude", "hermes", "openai"]` (id 排序)。原断言漏基线 hermes — 修测试
   为三元素列表, 实现零改动。
3. **test_find_by_capability_no_substring (测试期望错, 修测试)**: `chatty` 的
   openai 不精确匹配 `chat` (子串语义正确, 验证保留); 但默认 hermes 基线
   精确 `chat` 仍命中 → 断言 `["hermes"]` 而非 `[]`。实现零改动。

三例均为"测试期望错": 实现语义 (原始字符数 / 合并视图精确匹配) 与设计
docstring 自洽, 无任何设计文档定义相悖语义; 按既定仲裁 (backend-developer
skill: 判定依据 = 同仓代码设计 docstring/契约), 修测试不修实现。

## 影响

- 新增: `factory-core/providers/**` (models/store/definitions/registry/provider/
  events/adapters), CLI provider 子命令, Dashboard Provider View。
- 零改动: runtime/**, runtimes/** 及全部既有 Core; events store/logger/metrics。
- 测试: tests/providers/ (150) + tests/dashboard/ Provider View 用例;
  全量 2460 绿 (Phase 8A 收尾)。
