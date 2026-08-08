# Provider 选择模型 (provider-selection-model)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 通用 AI Software Factory 的 Provider 选择体系:Agent Task Requirement →
> Provider Capability 匹配模型、成本感知推荐流程,以及"只推荐不自动切换"语义。
> 依据 Phase 8B-2 (ADR-0024) 落地,与 Provider 扩展模型 (Phase 8A, ADR-0022) 和
> Provider 执行集成 (Phase 8B-1, ADR-0023) 衔接。

---

## 1. 核心公理

1. **能力必须要有证据**:Provider 说"能做什么"必须落到能力矩阵 (capability →
   质量分 0-1) + evidence (基准/文档/实测)。矩阵缺失的能力视为 **0.0 分 = 无能力**,
   不臆造 — 否则 vision=0.0 的无能力 Provider 会在默认门槛 (min_quality=0.0) 下
   被推荐 (冒烟实测抓出,三处语义修正)。
2. **推荐 ≠ 切换**:系统只产出 Recommendation (provider_id + score + reasons),
   **永不自动修改任何配置**。是否采纳由用户/调用方决定 — 采纳与否的后果由
   采纳方承担,推荐器零副作用。
3. **成本是估算,不是计费**:成本模型是定价估算 (token/request/time/free 模式
   归一),用途是排序依据与审计展示;真实计费/支付/预算强制明确为非目标。
4. **宁缺毋滥**:无通过能力过滤的候选 → 返回 None,不推荐无能力证据的 Provider。

---

## 2. 匹配模型:Task Requirement → Capability

### 2.1 TaskRequirement (输入)

Agent 任务对 Provider 的能力要求 (providers/models.py):

| 字段 | 类型 | 缺省 | 语义 |
|:-----|:-----|:-----|:-----|
| `task_type` | str | `"development"` | 任务类型键,与 `runtime_preferences.<task_type>` 键同构 |
| `required_capabilities` | list[str] | `[]` | 任务所需能力标签 (如 code/reasoning/vision) |
| `min_quality` | float | `0.0` | 能力质量门槛 0-1 (0.0 = 键存在即可) |
| `budget` | float \| None | `None` | 估算成本上限 USD (超出过滤;None = 不设限) |

### 2.2 ProviderCapabilityProfile (Provider 侧描述)

| 字段 | 语义 |
|:-----|:-----|
| `provider_id` | Provider id (与目录定义一致) |
| `matrix` | capability → 质量分 0-1;缺失能力 quality() 返回 0.0 |
| `max_tokens` / `context_window` | 窗口上限 (None = 未知/不限制) |
| `evidence` | 能力来源依据列表 (benchmark/vendor docs/measured) — 审计追溯用 |

### 2.3 匹配语义 (capability.py)

```
quality(capability)          → matrix.get(cap, 0.0)        # 缺失 = 0.0
has(capability, min_quality) → cap in matrix AND quality >= min_quality
                              # ★ 键存在且有证据;min_quality=0.0 是"键存在即可",
                              #   不是"0 分也通过"
score (required 非空)        → 各 required 能力 quality 的算术平均
score (required 空, 有矩阵)  → 整体矩阵平均
score (required 空, 无矩阵)  → 1.0 (无要求即完全匹配)
```

- `rank_for_task` 纯函数:能力过滤 + 质量分降序排序 (无存储依赖)。
- `find_best_for_task`:rank 首个 (无候选 → None)。

---

## 3. 选择流程 (CostAwareSelector.recommend)

五步 (providers/selector.py,phase8b2-plan.md §4):

```
┌─ 1. 能力过滤 ──────────────────────────────────────────────┐
│  registry.list() 中 ACTIVE 定义:                            │
│  · 无 capability profile → 跳过 (无能力证据不推荐)           │
│  · required 任一能力 !has(cap, min_quality) → 跳过           │
│  · budget 非 None 且估算成本 > budget → 跳过                 │
│  score = required 平均质量分                                 │
├─ 2. 配置优先 ──────────────────────────────────────────────┤
│  复用 ProviderSelector.resolve 四层链 (Phase 8B-1 保持):     │
│  explicit (CLI --provider) > project > agent > runtime      │
│    > default — 配置选中且过能力过滤 → 直接推荐               │
│  (reasons 标注"配置优先");配置选中但能力不足 → 推荐能力匹配   │
│  的替代并注明理由,不返回 None                                │
├─ 3. 成本感知排序 ──────────────────────────────────────────┤
│  min(_cost_sort_key):                                      │
│  · 估算成本升序 (free=0 优先;无成本模型 None 排最后)          │
│  · 同成本 → 质量分降序 → provider_id 字典序                  │
├─ 4. 只推荐 ────────────────────────────────────────────────┤
│  返回 Recommendation (provider_id/score/reasons/           │
│  estimated_cost/source="recommendation")                   │
│  无候选 → None (宁缺毋滥)                                   │
├─ 5. 记录 ──────────────────────────────────────────────────┤
│  调用方 (CLI) 发 provider.viewed + provider.selected        │
│  (source=recommendation, stage=recommended) — 只审计        │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 能力过滤的"键存在"语义 (三处一致)

`has(cap, min_quality)` 必须**键存在且有证据**才返回 True。该语义在
capability.py (`has`) / rank_for_task / selector._capability_candidates
三处一致 — 冒烟实测:vision=0.0 的 Provider 在 min_quality=0.0 下被推荐,
修三处后不再出现。**0 分不是能力,键缺失更不是能力。**

### 3.2 成本模式归一 (costs.py)

| 模式 | pricing | 一次调用估算 |
|:-----|:--------|:-------------|
| token | `{input: $/1K, output: $/1K}` | `in*pi/1000 + out*po/1000` (基准 ESTIMATED_TOKENS = 1000/500) |
| request | `{request: $/次}` | 单价 × 次数 (缺省 1) |
| time | `{per_hour: $/h}` | 单价 × duration_seconds/3600 (缺省 60s 基准) |
| free | `{}` | 恒 0.0 (本地模型,排序最优先) |

`estimate_call_cost(None)` → None (无法估算 → 排序排最后,不臆造 0)。
缺成本模型 ≠ 免费 — 只有 mode=free 才按 0 计。

### 3.3 配置优先的降级语义

- 配置层选中且过能力过滤 → 直接推荐 (reasons: "配置优先: <source> 层指定且
  能力满足要求") — 配置即用户意图。
- 配置层选中但能力不足 → **仍推荐**能力匹配的替代 (reasons 注明"配置 provider
  X 能力不满足要求,推荐能力匹配的替代") — 不返回 None。
- explicit 层 (CLI --provider) 未注册/禁用 → 抛 ProviderNotFoundError (用户
  意图须显式暴露,同 Phase 8B-1 契约)。

---

## 4. "只推荐不自动切换"语义

- **推荐器零副作用**:recommend() 不写任何配置 (project.yaml /
  catalog.json / runtime_preferences 全部不动),不触发执行。
- **事件是审计不是动作**:CLI 发 provider.selected (source=recommendation,
  stage=recommended) 只记录"推荐过什么",与选择链 source
  (explicit|project|agent|runtime|default) 严格区分 (评审调整 4)。
- **采纳路径**:用户按 recommendation.provider_id 显式配置 (project.yaml /
  CLI --provider),之后走 Phase 8B-1 的选择链 — 推荐与选择是两件事。
- **推荐器与选择器分离**:CostAwareSelector 独立于 ProviderSelector 存在,
  resolve() 零改动 (Phase 8B-1 兼容性保持)。

---

## 5. 数据与存储边界

| 数据 | 位置 | 说明 |
|:-----|:-----|:-----|
| Provider 定义 | `providers/catalog.json` + 代码层默认基线 | 核心目录数据,损坏 → 响亮报错 (CorruptProviderStoreError) |
| 能力/成本基线 | 代码层 `DEFAULT_CAPABILITY_PROFILES` / `DEFAULT_COST_MODELS` | 只读基线;自定义 Provider 数据由调用方注入 |
| Usage 记录 | `providers/usage.json` (独立数据空间) | 原子写;损坏 → 失败安全 (读命令永不因 usage 失败) |
| 性能聚合 | 从 usage 计算,不落库 | stats_from_usage 纯函数 |

损坏语义分界:usage.json 是**审计增强数据** → 损坏/单条校验失败 → 跳过/空,
append 从空重建;catalog.json 是**核心目录数据** → 损坏 → 响亮失败。

---

## 6. CLI 入口

```
factory provider recommend --task <type> [--capabilities a,b]
    [--min-quality F] [--budget F]     → 能力匹配 + 成本感知推荐 (发 provider.* 审计)
factory provider usage [--provider X] [--period day|week|all]
                                       → 使用记录 (估算成本,非真实计费)
factory provider stats [--provider X] [--period day|week|all]
                                       → 性能聚合 (provider/model/version/period)
factory provider compare <a> <b>       → 能力/成本对比 (估算模型)
```

推荐为空 (无通过候选) → rc 0 + recommended=None (宁缺毋滥,非错误)。

---

## 7. 非目标

- 不实现真实计费/支付;预算只做推荐过滤,不强制执行。
- 不自动切换 Provider — 只提供选择依据 + 审计记录。
- 不修改 Core (ExecutionRunner 不动;usage 记录经 CLI/集成层)。
- 不实现 OpenAI/Claude Adapter (连接器留待后续阶段)。
