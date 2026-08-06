# Phase 8B-2 Plan — Provider Capability & Cost Layer

> 日期: 2026-08-06 | 状态: 架构设计评审, 待确认
> 冻结约束: Core 零修改 / Extension 独立 / 暂不实现真实计费

## 1. 核心洞察

Provider 不只是连接器。Provider 应该描述:

```
能做什么 (Capability)    能力矩阵: 任务类型 × 能力 × 质量指标
成本多少 (Cost)          定价估算模型 (per-token/固定费率/免费)
表现如何 (Performance)   延迟/成功率/吞吐 (从 usage 记录聚合)
```

为未来自动选择 AI 做准备: Selector 从"静态配置"升级为"能力匹配 + 成本感知"。

## 2. 模块边界 (factory-core/providers/ 扩展, 独立 Extension)

```
factory-core/providers/
├── models.py            (已有: ProviderDefinition) + ProviderCapabilityProfile + ProviderCostModel
│                        + ProviderUsage + ProviderPerformanceStats
├── capability.py        能力矩阵 + 查询 (find_best_for_task: 能力过滤 → 成本排序)
├── costs.py             成本估算模型 (配置化定价表, 非真实计费)
├── usage.py             UsageStore (.factory/providers/usage.json 独立数据空间)
├── selector.py          (已有) + CostAwareSelector 增强 (能力感知选择)
├── events.py            (已有) + provider.usage.recorded
└── ...
```

## 3. 数据模型

```python
class ProviderCapabilityProfile(Pydantic):
    provider_id: str
    matrix: dict[str, float]    # capability → quality score 0-1 (chat=0.9, code=0.8, vision=0.0)
    max_tokens: int | None
    context_window: int | None
    evidence: list[str]         # 能力来源依据 (基准/文档/实测) [评审调整 1]

class ProviderCostModel(Pydantic):
    provider_id: str
    mode: str                   # token | request | time | free [评审调整 2]
    pricing: dict[str, float]   # 按模式: {input: x, output: y} / {request: x} / {per_hour: x} / {}
    currency: str = "USD"
    free: bool = False          # 本地模型免费

class ProviderUsage(Pydantic):
    id: str; provider_id: str; execution_id: str | None
    prompt_tokens: int; completion_tokens: int
    estimated_cost: float       # 由 CostModel 估算 (非真实计费)
    latency_ms: int
    success: bool
    error: str | None
    recorded_at: str

class ProviderPerformanceStats(Pydantic):
    provider_id: str
    model: str | None           # [评审调整 3]
    version: str | None         # [评审调整 3]
    period: str                 # 聚合周期 (day/week/all) [评审调整 3]
    calls: int; success_rate: float
    avg_latency_ms: float; total_tokens: int; total_cost: float

class TaskRequirement(Pydantic):      # [评审调整 5] Agent Task Requirement → Provider Capability 匹配
    task_type: str                    # development/testing/analysis/docs
    required_capabilities: list[str]
    min_quality: float = 0.0
    budget: float | None              # 成本上限 (估算)
```

## 4. 能力描述与自动选择

```
CostAwareSelector.recommend(task_requirements: TaskRequirement, preferences, registry):
  1. 能力过滤   capability.matrix[req] >= min_quality (含 evidence 依据)
  2. 配置优先   显式项目配置 > Agent > Runtime > Default (保持 Phase 8B-1 链)
  3. 成本感知   多候选按 estimated_cost 升序 (token/request/time/free 模式归一估算)
  4. 只推荐    返回 Recommendation (provider_id + score + reasons) — 不自动切换 [评审调整 4]
  5. 记录       provider.selected (source=recommendation) + usage 记录
```

## 5. 成本/性能数据接口

```
接口: ProviderUsage.record(usage) → UsageStore (每次调用记录)
聚合: ProviderPerformanceStats.from_usage(store) → 延迟/成功率/成本
CLI:  factory provider usage [--provider X]    — 使用记录
      factory provider stats [--provider X]    — 性能聚合
      factory provider compare <a> <b>         — 能力/成本对比
Dashboard: Provider View 增强 (usage/cost/performance 列)
```

## 6. 事件

```
provider.usage.recorded (payload: provider_id/execution_id/tokens/estimated_cost/latency/success)
经 EventLogger; 既有 provider.* 事件不变
```

## 7. 存储边界

| 数据 | 位置 | 说明 |
|:-----|:-----|:-----|
| 能力/成本模型 | catalog.json 扩展或独立 capability.json | providers/ 数据空间 |
| Usage 记录 | .factory/providers/usage.json | 独立, 原子写 |
| 性能聚合 | 从 usage 计算 (不落库) | 事件驱动 |

## 8. 非目标

- 不实现真实计费/支付
- 不实现预算强制执行
- 不自动切换 Provider (只提供选择依据 + 记录)
- 不修改 Core (ExecutionRunner 不动; usage 记录经 CLI/集成层)

## 9. 测试策略 (预计 ≥80)

- CapabilityProfile (矩阵/质量分/查询)
- CostModel (定价估算/flat/免费)
- UsageStore (记录/聚合/原子写/损坏)
- CostAwareSelector (能力过滤/成本排序/优先级保持)
- 事件 (usage.recorded payload)
- CLI (usage/stats/compare)
- Dashboard 增强
- 兼容性 (Phase 8B-1 选择链不变)
- Removal Isolation

## 10. 确认要点

1. ✅ Core 零修改 (providers/ 内部扩展)
2. ✅ Extension 独立 (独立数据空间 usage.json)
3. ✅ 能力描述模型 (CapabilityProfile 矩阵)
4. ✅ 自动选择准备 (CostAwareSelector)
5. ✅ 成本/token/性能接口 (Usage + Stats + CLI)
6. ✅ 暂不实现真实计费
7. ✅ 不实现 OpenAI/Claude Adapter (连接器后续)
