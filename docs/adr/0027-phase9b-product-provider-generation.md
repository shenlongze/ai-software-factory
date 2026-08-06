# ADR-0027 — Phase 9b: Product Provider 生成层

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Factory 需要把 LLM Provider (Phase 8) 接入产品阶段: 经 Provider Intelligence
(CostAwareSelector) 自动选择 Provider 生成产品 Artifact (research/prd/ui), 生成后
PRD/UI 自动申请人工审批 (9a Approval Gate 联动), 并把人工对生成产物的经验
(Experience) 落库作为后续优化数据接口。本阶段只实现**生成框架** (编排 + 上下文
记录 + 经验记录), 不实现复杂 Prompt, 不实现 Provider 侧优化逻辑。

## 决策

### 1. 生成编排链 (禁硬编码 / 禁直接调 LLM)
`ProductGenerator.generate` 编排: idea 存在性校验 → TaskRequirement 构造 →
`CostAwareSelector.recommend` (复用 Phase 8 只读调用, 零修改) →
`ProviderAdapter.generate` (适配器映射由 CLI 装配点注入, 本模块不 import 任何
Adapter 实现) → Artifact 产出 (content 含 `generation_context` +
`content` = Provider 返回内容, status=completed) → PRD/UI 自动
`request_approval` (mandatory, 生成后等待人工批准) → GenerationResult。
GENERATION_TYPES 是**领域映射** (research→analysis / prd→generation+reasoning /
ui→generation; 门: prd/ui mandatory, research 无默认门), 不是 Provider 硬编码;
capabilities 必须落在默认 hermes 能力基线矩阵内, 否则默认配置直接 NoProviderError。

### 2. 事件链契约 (终态事件单一且承载完整信息)
成功链: `product.generation.started → provider.selected (source=product,
stage=recommended) → provider.execution.started → provider.execution.completed
→ [provider.usage.recorded, 失败安全] → product.generation.completed →
approval.required (PRD/UI)`。**product.generation.completed 在自动审批请求之后
统一发出一次** (payload 携带 approval_request_id), 不在审批前发"缺信息版"——
原实现先发一次 (approval=None) 再补发一次造成 PRD/UI 双 completed、research 单
completed 不一致 (收尾实测抓出, 测试用 `types.count(...) == 1` 断言回归)。
失败链: `... → product.generation.failed (result=ERROR)`, 无 completed。
通用规律: 同一事件类型在全部路径事件数必须一致; 事件在它报告的状态转换完成后发。

### 3. 失败语义双通道 (明确错误不静默)
无 selector / 无能力候选 / 无 Adapter 实现 → `product.generation.failed` 事件 +
明确异常 (ProductGenerationNoProviderError / ProductGenerationError), CLI 退出码
1, **不产出 Artifact** (配置缺口响亮暴露); adapter 实际调用失败 (error 响应或
意外异常) → usage 失败记录 (8B-3 语义: 落库失败跳过 BOTH) + execution.failed +
failed 事件 + raise, **并额外落 status="failed" Artifact** (Lineage 保留
provider_id/version, 失败产物可追溯 — 9a "幻影产物"教训的失败侧; Dashboard
generation 状态列数据源; 收尾裁定: 模块 docstring 声明 + 测试要求, 翻转设计参考
"本阶段选择不产"的取舍)。

### 4. Removal Isolation 新变体: 消费方响亮失败
装配点 `_open_product_generator` ImportError → selector/adapters/usage_store 全
None; **消费方 (ProductGenerator) 对 None 依赖抛明确错误 + 发 generation.failed**
(CLI rc 1), 不静默跳过 — "删除 providers = product generate 响亮 rc 1, 其余命令
零影响"。`product/__init__.py` 故意不导出 generation (providers 专用消费方) — 删
providers 后 `import product` 仍成功; generation.py 顶层 import
providers.models/usage (I/O 契约类型, 本职就是 provider 编排), 禁顶层 import
providers/adapters (Adapter 实现); providers.events 辅助在方法内延迟 import。

### 5. Experience 经验记录 (数据接口, 不实现优化逻辑)
GenerationExperience (artifact_type/provider_id/approved/confidence/human_feedback/
rating 1-5/generated_at/recorded_at) 落独立文件 `<root>/product/experience.json`,
**损坏失败安全** (审计增强数据, 同 UsageStore — 区别于 ProductStore 核心数据响亮
报错); record 从 Artifact Lineage 推导 provider_id/confidence/generated_at —
经验与 Lineage 闭环; approved 由 CLI `--approved true|false` 显式传 (不与
ApprovalRequest 状态自动耦合)。CLI: `product experience record <artifact_id>
--rating 1-5 [--comment] [--approved true|false] [--by]` (未找到 rc 7) / `list
[--artifact-type]` (发 experience.viewed 审计, ADR-0002 读命令必须产生事件)。

### 6. 兼容扩展: 写入口加可选参数用 `None → 旧默认`
`service.create_artifact(..., version: int | None = None)` — None → 1, 既有调用/
测试零影响 (Pyright reportCallIssue 自动标漏改调用点)。与既有"装配辅助函数加参数
须同步全部调用点"互为镜像 (服务层写入口同样 keyword-only + None 兜底)。

### 7. CLI 接线 (4 触点 + argparse 陷阱)
main.py imports / 解析器 (`product generate <idea_id> --type research|prd|ui
[--provider]` — choices 前置拦截无效类型 → SystemExit(2); `product experience
<list|record>`) / `_dispatch_product` / `_print_product` (须传 args 让叶子命令决定
事件名, 9a 教训)。**布尔选项禁用 `type=bool`** (argparse 的 `type=` 直接调
`bool(v)`, `bool("false")` 是 True) — `--approved` 用显式字符串解析 helper
`_parse_optional_bool` (true/1/yes→True, false/0/no→False, 其余
ArgumentTypeError; default=None 保持未判定语义)。

### 8. 收尾裁定 (Phase 9b 收尾实测)
- **测试 helper bug 2 处** (修 tests/product/product_helpers.py): `make_generator`
  的 `selector=None` 被"缺省=mock"兜底吞掉 → 显式 None 无法表达"未装配"; 同款
  `MockSelector(recommendation=None)` 应模拟"无候选"却回退默认推荐。修法: 哨兵
  `_UNSET` 区分"未传参"(→ 默认 mock) 与"显式 None"(→ 透传 None)。连带修复
  3 个失败测试 (selector 未装配 ×2 + 无候选 + CLI 事件链 no-provider)。
- **测试 setup bug 1 处** (修 test_product_generator.py): 显式 provider 覆盖测试
  把推荐指向 "auto" 但 adapters 映射只注入 "mock" → 误入无 Adapter 失败路径;
  补注入 `adapters={"auto": ...}` (显式 provider 必须有对应实现, 测试自洽)。
- **实现 bug 2 处** (修 factory-core/product/generation.py): (a) adapter 失败
  未落 failed Artifact (模块 docstring 声明"adapter 失败额外产出 status='failed'
  的 Artifact"与实现不符 — 9a 幻影产物教训的失败侧, 见决策 3); (b)
  GeneratedArtifactContext.generation_time 校验只认内部规范格式, 拒绝合法 ISO 8601
  UTC 时间戳 (`2026-08-06T12:00:00Z` — 与自身错误信息 "must be a UTC timestamp"
  矛盾); 修法: 校验接受规范格式或 ISO 8601 Z/+00:00 (naive 时间戳仍拒绝),
  不动事件库的 parse_timestamp 严格格式。
- 收尾补测 6 个 CLI 测试 (tests/product/test_product_generation_cli.py):
  generate prd → Artifact + approval pending + 单一 completed 事件链 / generate
  --json 形状 (research 无 approval) / idea 未找到 rc 7 / 无效类型 SystemExit(2) /
  experience record+list (事件审计) / record 未找到 rc 7。

## 影响

- Core 零修改; providers/** 只读复用 (CostAwareSelector/ProviderAdapter/Usage)。
- product/ 纯新增: generation.py + experience.py + events.py (+5 辅助) +
  service.py 一处最小扩展 (version 参数)。
- EventType +5 枚举成员 (纯增量, 不改表不破坏既有测试)。
- Dashboard ProductSnapshot +5 字段 (generation_total/generations_by_status/
  generations/experience_total/experiences, 全默认空 — 零回归), collector
  experience_store 参数默认 None。
- 测试: 3135+7 失败 → 修 7 + 补 6 → 全量 3148 passed。
