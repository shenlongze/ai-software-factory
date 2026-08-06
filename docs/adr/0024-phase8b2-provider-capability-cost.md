# ADR-0024 — Phase 8B-2: Provider 能力 + 成本 + 使用层 (能力匹配与成本感知推荐)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 8B-1 (ADR-0023) 把 Provider 接入 Execution 流程 (四层选择链 +
载波注入),但选择仍是**静态配置** — 只回答"配置了谁",不回答"谁更能胜任
这个任务、成本多少、表现如何"。Provider 目录 (ADR-0022) 也只有能力标签,
没有量化证据。

Phase 8B-2 补上三层 (phase8b2-plan.md §3):

- **Capability**: `ProviderCapabilityProfile` 能力矩阵 (capability → 质量分
  0-1 + evidence 依据) + `TaskRequirement` (Agent 任务能力要求)。
- **Cost**: `ProviderCostModel` 定价估算模型 (token/request/time/free 四模式
  归一, 非真实计费)。
- **Usage**: `ProviderUsage` + `UsageStore` (每次调用记录, 独立数据空间
  usage.json) + `ProviderPerformanceStats` (provider/model/version/period
  聚合, 从 usage 计算不落库)。

推荐器 `CostAwareSelector` 把三者合一:能力过滤 → 配置优先 → 成本排序 →
**只推荐不自动切换**。冻结约束: Core 零修改; usage 记录经 CLI/集成层;
不实现真实计费/支付; 不自动切换 Provider。

本 ADR 记录: 能力过滤"键存在"语义 (三处修正)、CostAwareSelector 五步流程、
CostModel 四模式归一、UsageStore 损坏失败安全 vs ProviderStore 报错的设计
分界、Dashboard 零回归列增强, 以及收尾 5 个失败测试的契约裁定 (2739 + 5
failed → 2744 全绿)。

## 决策

### 1. TaskRequirement → Capability 匹配模型 (评审调整 5)

`providers/models.py` 新增 `TaskRequirement`:

- `task_type`: 任务类型键 (development/testing/analysis/docs..., 与
  `runtime_preferences.<task_type>` 键同构 — 推荐器配置优先层直接复用
  四层链的 task_type 键)。
- `required_capabilities`: 任务所需能力标签; `min_quality`: 质量门槛 0-1
  (缺省 0.0); `budget`: 估算成本上限 USD (None = 不设限)。
- 匹配语义 (capability.py): `quality()` 缺失能力 → 0.0; `has()` 要求
  **键存在且 quality >= min_quality**; score = required 平均质量分。

### 2. ★ 能力过滤"键存在"语义 (三处一致, 冒烟实测修正)

- 问题: 初版 `has(cap, 0.0)` 用 `quality(cap) >= min_quality` 判断 — 矩阵
  缺失的能力 quality() 返回 0.0, 在默认门槛 min_quality=0.0 下 **0 >= 0 恒
  真** → vision=0.0 的无能力 Provider 被推荐 (冒烟实测抓出)。
- 裁定: 能力必须有**证据**才参与推荐。`has` 改为
  `capability in self.matrix and quality(capability) >= min_quality` —
  min_quality=0.0 表示"键存在即可", 不是"0 分也通过"。
- 修正三处 (保持语义一致): `capability.py has` / `rank_for_task` 过滤条件 /
  `selector._capability_candidates` 过滤条件。实现 bug, 修实现。

### 3. CostAwareSelector: 能力过滤 → 配置优先 → 成本排序 → 只推荐

`providers/selector.py` (独立类, ProviderSelector 零改动 — Phase 8B-1
兼容):

1. **能力过滤**: registry.list() 中 ACTIVE 定义; 无 profile → 跳过 (无能力
   证据不推荐); required 任一能力不过 `has` → 跳过; budget 超限 → 跳过。
   score = required 平均质量分 (required 空 → 矩阵平均 / 无矩阵 1.0)。
2. **配置优先**: 复用 ProviderSelector.resolve 四层链 (explicit > project >
   agent > runtime > default, ADR-0023 保持) — 配置选中且过能力过滤 → 直接
   推荐 (reasons 标注"配置优先"); 配置选中但能力不足 → 推荐能力匹配替代并
   注明理由, **不返回 None**; explicit 未注册/禁用 → ProviderNotFoundError
   (用户意图显式暴露)。
3. **成本感知排序**: `_cost_sort_key` — 估算成本升序 (free=0 优先; 无成本
   模型 None 排最后), 同成本质量分降序, 再 provider_id 字典序。
4. **只推荐**: 返回 Recommendation (provider_id/score/reasons/estimated_cost/
   source="recommendation"), 无候选 → None (宁缺毋滥)。
5. **记录**: 调用方发 provider.selected (source=recommendation, stage=
   recommended) — 只审计, 不自动切换任何配置 (评审调整 4)。

数据注入: capability_profiles/cost_models 构造参数 (dict id → 模型), 缺省
空 dict; registry 装配时配置层做存在性/状态校验 (同 ProviderSelector)。

### 4. CostModel 四模式归一 (评审调整 2)

`providers/costs.py` — 多模式定价估算 (非真实计费):

- token: `{input: $/1K, output: $/1K}` → `in*pi/1000 + out*po/1000`
  (基准 ESTIMATED_TOKENS = 1000/500, 常量即文档)。
- request: `{request: $/次}` → 单价 × 次数 (缺省 1)。
- time: `{per_hour: $/h}` → 单价 × duration_seconds/3600 — **duration_seconds
  必填否则 ValueError** (估算基准 ESTIMATED_DURATION_SECONDS = 60)。
- free: 恒 0.0 (本地模型, 排序最优先)。

`estimate_call_cost(None)` → None (无法估算 → 排序排最后, **不臆造 0** —
缺成本模型 ≠ 免费)。`estimate_call_cost` 捕获 ValueError → None (定价键
缺失失败安全)。estimate_cost 本身抛 ValueError (time 缺时长 / token 缺键) —
模型契约, 调用方兜底。

### 5. UsageStore: 损坏失败安全 vs ProviderStore 报错 (设计分界)

`providers/usage.py` — `<root>/providers/usage.json` 独立数据空间 (与
catalog.json 同目录不同文件, phase8b2-plan.md §7):

- **写**: 原子写 (临时文件 + os.replace); record 前 `mkdir(parents=True)`。
- **读失败安全** (usage = 审计增强数据): 文件不存在 → 空; JSON 坏 → 空;
  结构坏 (非 dict / 无 records list) → 空; **单条校验失败 → 跳过保留可读
  部分**; append 在损坏文件上从空重建。读命令 (list/count) 永不因 usage
  文件失败。
- **对照**: ProviderStore (catalog.json = 核心目录数据) 损坏 → 响亮抛
  CorruptProviderStoreError — 核心数据不静默吞错。
- period 过滤 (filter_by_period): day=今天 / week=最近 7 天 / all; 非法
  period → ValueError (CLI choices 前置拦截); 时间戳坏 → 跳过。
- stats_from_usage: (provider_id, model, version) 三维分组 (评审调整 3),
  口径: success_rate = 成功/总数 (0 调用 → 0.0), avg_latency/total_tokens/
  total_cost 累计; 失败调用也记录 (success=False + error)。

### 6. Dashboard 可选列增强 (零回归变体, 非新视图)

- ProviderSnapshot 加 `usage_*` 字段 (默认 0/空); build_provider **仅当
  usage_total_calls > 0 时追加列** — 无数据逐位不变, 不加新视图 →
  VIEWS 精确集合断言 (len == 18) 零破坏。
- collector 加 usage_store 构造参数默认 None (无 usage 数据 → 零列)。

### 7. 默认基线: 能力/成本模型常驻代码层 (同 ADR-0014 决策 3 模式)

`providers/definitions.py` 新增 `DEFAULT_CAPABILITY_PROFILES` /
`DEFAULT_COST_MODELS` (hermes: 六能力矩阵估算分 + free 成本模型) — 只读
基线, 读路径合并; 持久化覆盖 (capability.json/costs.json) 留待后续阶段
(本阶段 KISS: 自定义 Provider 的能力/成本数据由调用方注入 CostAwareSelector)。

## 影响

- 新增: `factory-core/providers/capability.py` (ProviderCapabilityProfile +
  rank_for_task/find_best_for_task), `factory-core/providers/costs.py`
  (ProviderCostModel + estimate_call_cost + 基准常量), `factory-core/
  providers/usage.py` (ProviderUsage/ProviderPerformanceStats/UsageStore/
  filter_by_period/stats_from_usage); models.py 增 TaskRequirement;
  selector.py 增 CostAwareSelector/Recommendation/RECOMMENDATION_SOURCE;
  definitions.py 增默认能力/成本基线。
- 修改: `factory-core/cli/main.py` (provider recommend/stats/usage/compare
  子命令), `factory-core/cli/commands.py` (四命令 + _open_provider_usage_store);
  events/models.py 增 provider 使用计量 payload 字段 (Phase 8A/8B-1 载荷
  契约零破坏)。
- 零改动: Core (execution/workflows/runtime/runtimes/orchestration); events
  store/logger/metrics 主路径; Dashboard 视图集合 (零回归列增强)。
- 测试: tests/providers/ (capability/costs/usage/selector 8B-2 + 既有 8A/8B-1
  兼容 + removal isolation), 全量 **2744 绿** (Phase 8B-2 收尾)。
- 冒烟验证: provider recommend --task development --capabilities
  code,reasoning → 推荐 hermes (能力匹配 + free 成本); provider stats /
  usage → 空库 rc 0; provider compare hermes <other> → 能力/成本对比列。
- 收尾修复: 5 个损坏失败安全测试失败根因 = conftest providers_dir fixture
  未预建目录, 测试在构造 UsageStore 前直接写损坏 usage.json 触发
  FileNotFoundError (backend-developer skill 陷阱: 损坏文件测试先
  mkdir(parents=True)); 实现 (UsageStore._write_all 已 mkdir、读路径失败
  安全) 正确 — 测试夹具缺口, 修 fixture 不修实现 (最小 diff: fixture
  加 mkdir(parents=True, exist_ok=True))。2739 + 5 failed → 2744 全绿。
