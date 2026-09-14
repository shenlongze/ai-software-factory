# LLM 智能路由 — 设计说明 & 实施蓝图 (给 Hermes)

> 版本: v1.0 | 日期: 2026-08-13 | 状态: 待实施 (S10-021+)
> 读者: Hermes (Orchestrator) 与实现 Sub-agent
> 目标: 让 LLM 路由从"骨架 (70%)"到"智能+可配置+经验三要素完整 (100%)"
> 关联: 项目快照 §9 (Provider & Model 现状) + 审查报告 §9/§10 (Provider + Routing)

---

## 0. 一句话定义

**LLM 智能路由 = 系统按"任务特征 + 用户配置 + 历史经验"动态选出最优模型执行,可解释、可覆盖、越用越准。**

```
指定 (用户说了算) > 规则配置 (用户定规则) > 智能推荐 (系统动态选) > 内置兜底
```

---

## 1. 现状盘点 (代码真实状态, 实施前必须读)

### 1.1 已存在 (骨架, 70%)

| 文件 | 内容 | 完整度 |
|:---|:---|:---|
| `providers/provider.py` | ProviderAdapter 抽象, ProviderRegistry (纯内存), ProviderConfigChecker (key 预检) | ✅ |
| `providers/selector.py` | ProviderSelector.resolve (四层链), CostAwareSelector.recommend (能力过滤+三分数) | ✅ |
| `providers/costs.py` | ProviderCostModel, estimate_call_cost | ✅ |
| `providers/usage.py` | ProviderUsage, UsageStore, ProviderPerformanceStats, performance_score_from_stats | ✅ |
| `providers/feedback.py` | ProviderFeedback, FeedbackStore | ✅ |
| `providers/config.py` | preferred_provider, parse_runtime_preferences (project.yaml) | ✅ |
| `providers/capability.py` | ProviderCapabilityProfile, rank_for_task, find_best_for_task | ✅ |
| `providers/events.py` | provider.selected / usage.recorded 审计 | ✅ |

**测试**: 569 个 providers 测试全绿 — 骨架是被验证过的。

### 1.2 缺失 (三块, 实施目标)

| 缺 | 现状 | 要补成 |
|:---|:---|:---|
| **① 模型粒度** | 只选 Provider (anthropic/openai/deepseek) | 选具体 Model (deepseek-v4-flash vs pro) |
| **② 动态权重** | score = 0.4×capability + 0.3×cost + 0.3×performance (硬编码) | 按任务类型动态调权重 |
| **③ 经验回馈** | usage/feedback 存了但没消费 | 历史表现 → 影响下次推荐 (越用越准) |

---

## 2. 目标架构 (三要素完整形态)

```
┌────────────────────────────────────────────────────────────┐
│  LLM Router (新: 统一入口)                                  │
│  route(task, context, user_constraints) → ModelChoice       │
│  ModelChoice = {model_id, provider_id, score, reasons,       │
│                 can_override: [model_a, model_b]}            │
├────────────────────────────────────────────────────────────┤
│  ① 模型目录 ModelCatalog (新)                               │
│     model_id → {provider, capability, context_window,        │
│                  cost_per_mtok, availability, enabled}       │
│  ② 选择链 (升级 CostAwareSelector)                          │
│     指定 > 规则配置 > 智能推荐 > 兜底                        │
│  ③ 动态权重 (按任务类型)                                    │
│     code→质量0.5 分析→质量0.4 批处理→成本0.5 交互→速度0.5   │
│  ④ 经验回馈 (接 usage+feedback)                             │
│     历史表现分 → 加权进评分                                  │
├────────────────────────────────────────────────────────────┤
│  存储 (持久化)                                              │
│  ~/.factory/providers.json (Provider 配置, 已有目录空)      │
│  ~/.factory/model-catalog.json (模型目录, 新)               │
│  usage/feedback 已有 Store                                  │
└────────────────────────────────────────────────────────────┘
```

---

## 3. 三层控制 (可配置的核心)

用户有三层控制权,从"完全手控"到"完全智能":

```
第1层 完全指定 (最高优先): 
  用户: "这个任务用 deepseek-v4-pro" / "这个项目只用本地"
  → 硬规则, 不智能, 最可控
  → 来源: CLI 参数 / 单任务配置 / 对话指令

第2层 规则配置 (用户定规则, 系统执行):
  project.yaml model_routing:
    default: deepseek-v4-flash
    by_task:
      code: deepseek-v4-pro
      analysis: gpt-4o
      simple: local-ollama
    sensitivity: {sensitive: local-ollama}
    budget: {monthly: 500, over_budget: downgrade}
  → 半智能, 系统按规则路由

第3层 智能推荐 (系统建议, 用户可覆盖):
  系统: "推荐 deepseek-v4-pro (代码历史质量4.5/5 + 成本3元/百万), 可换?"
  → 全智能, 用户一键接受/覆盖
  → 可解释: 每次路由带 reasons
```

**优先级链 (统一): 指定 > 规则配置 > 智能推荐 > 内置兜底**

---

## 4. 智能推荐的核心: 四信号 + 动态权重

### 4.1 四信号

| 信号 | 来源 | 说明 |
|:---|:---|:---|
| ① 能力匹配 | ModelCatalog + TaskRequirement | 该模型能否胜任任务 (capability 过滤) |
| ② 历史质量 | usage + feedback 聚合 | 过去同类任务表现 (越用越准) |
| ③ 成本 | cost per million token | 输入+输出估算 |
| ④ 当前状态 | availability/enabled/latency | 可用性 (预留) |

### 4.2 动态权重 (按任务类型)

```
不是固定 0.4/0.3/0.3, 是按 task_type 动态调:

task_type=code        → capability 0.45, quality 0.25, cost 0.15, speed 0.15
task_type=analysis    → capability 0.35, quality 0.35, cost 0.15, speed 0.15
task_type=chat/simple → capability 0.20, quality 0.15, cost 0.30, speed 0.35
task_type=batch       → capability 0.25, quality 0.10, cost 0.45, speed 0.20

DEFAULT_WEIGHTS: capability 0.40, cost 0.30, performance 0.30 (兼容现有)
```

**实施**: `selector.py` 加 `weights_for_task_type(task_type) -> dict`, 现有 `_weight` 逻辑改为传入动态权重。

### 4.3 历史质量信号 (经验回馈)

```
每个执行完成 → 记 usage (model_id + task_type + result)
用户反馈 → feedback (model_id + task_type + rating)
聚合 → 历史质量分:
  model X 在 task_type=code 上: 
    成功次数 / 总次数 + 平均 rating → 0~1 分

回馈: score += 历史质量分 × quality_weight
冷启动: 无历史 → 中性 0.5 (不惩罚新候选)
```

**实施**: `usage.py`/`feedback.py` 加 `model_id` + `task_type` 字段 (数据口子), 新增聚合函数 `model_quality_score(model_id, task_type)`.

---

## 5. 模型粒度: Provider → Model

**关键升级**: 现在选 Provider, 要选具体 Model.

```
Provider (服务商): deepseek / openai / anthropic / local
  └─ Model (具体型号): deepseek-v4-flash, deepseek-v4-pro, gpt-4o, ...
     → 每个 Model: {provider, capability, context_window, cost, enabled}
```

**实施**: 新增 `ModelCatalog` (model-catalog.json):
```json
{
  "models": {
    "deepseek-v4-flash": {"provider": "deepseek", "capabilities": ["code","reasoning","chat"],
                          "context_window": 1000000, "cost_in": 1.0, "cost_out": 2.0,
                          "enabled": true, "availability": "cloud"},
    "deepseek-v4-pro":   {"provider": "deepseek", "capabilities": ["code","reasoning","chat"],
                          "context_window": 1000000, "cost_in": 3.0, "cost_out": 6.0,
                          "enabled": true, "availability": "cloud"},
    "local-ollama-qwen": {"provider": "local", "capabilities": ["chat","code"],
                          "context_window": 128000, "cost_in": 0.0, "cost_out": 0.0,
                          "enabled": true, "availability": "local"}
  }
}
```

---

## 6. 可解释 + 可覆盖 (用户敢用的前提)

每次路由必须返回可解释的选择 + 可覆盖项:

```
ModelChoice:
  model_id: "deepseek-v4-pro"
  reasons: [
    "任务=写代码 (质量权重 0.45)",
    "deepseek-v4-pro 代码能力 4.5/5 (同类任务历史最佳)",
    "成本 3元/百万 (比 claude 便宜 20倍)",
    "可用: 是"
  ]
  can_override: ["deepseek-v4-flash", "gpt-4o", "local-ollama-qwen"]
  source: "recommendation"  // 或 "explicit" / "rule" / "fallback"
```

**理由必须可解释**: 每项分数 + 方向 (+/-) + 来源。这也进审计 (audit capability 字段已有 {llm: {id, version}})。

---

## 7. 实施路径 (分三步, 不要一次做完)

### Step 1: 留数据口子 (最小, 先做) — 不改路由逻辑, 只补记录

```
1. usage.py: ProviderUsage 加 model_id 字段 (现在可能只记 provider_id)
2. feedback.py: ProviderFeedback 加 model_id + task_type 字段
3. 确保每次执行记下 model_id + task_type + result
→ 目的: 让现有执行自动积累"模型/任务/结果"数据, 为 Step 3 铺路
```

### Step 2: 模型粒度 + 动态权重 (核心升级)

```
1. 新增 ModelCatalog (model-catalog.json + Model 模型)
2. selector.py 加 weights_for_task_type(task_type)
3. CostAwareSelector.recommend 升级: 候选从"Provider"变"Model", 权重动态
4. 配置持久化: providers.json + model-catalog.json 加载
→ 目的: 从"选服务商"到"按任务动态选模型"
```

### Step 3: 经验回馈 + 可解释 (闭环)

```
1. 新增 model_quality_score(model_id, task_type) — 聚合 usage+feedback
2. recommend 评分纳入历史质量分 (冷启动中性 0.5)
3. 返回 ModelChoice (含 reasons + can_override)
4. 接审计 (audit capability {llm: {id, version}})
→ 目的: 越用越准 + 用户敢用
```

---

## 8. 验收标准 (每条可测)

| 验收 | 测试方法 |
|:---|:---|
| 模型粒度 | 配置多个 model, 路由返回具体 model_id (非 provider_id) |
| 动态权重 | 同任务不同 task_type, 权重不同 → 选不同模型 |
| 指定优先 | 用户指定 model → 忽略推荐, 用指定的 |
| 规则配置 | project.yaml by_task 生效 |
| 经验回馈 | 喂 usage/feedback 数据 → 历史质量分影响推荐 |
| 可解释 | 每次返回 reasons (分数+方向+来源) |
| 可覆盖 | can_override 返回候选, 用户换模型生效 |
| 持久化 | providers.json 重启不丢 |
| 审计 | 路由结果进事件流 (model 选择可追溯) |

---

## 9. 明确不做 (本设计范围外)

- ❌ 不做 Multi Agent 编排
- ❌ 不做 Memory / Learning Loop
- ❌ 不做故障切换/负载均衡 (预留接口, 后加)
- ❌ 不做 MCP 相关 (那是 Tool 层)
- ❌ 不改 AgentRuntime 主逻辑 (路由是独立模块)

---

## 10. 给 Hermes 的交接要点

1. **现状**: providers 骨架完整 (569 测试), 缺三块: 模型粒度/动态权重/经验回馈
2. **数据口子第一步**: usage/feedback 补 model_id + task_type (先做, 不阻塞)
3. **核心第二步**: ModelCatalog + 动态权重 (selector.py 升级)
4. **闭环第三步**: 经验回馈 + 可解释 (usage/feedback 聚合)
5. **优先级**: 数据口子 > 模型粒度+权重 > 经验回馈
6. **别重构**: 复用 CostAwareSelector/UsageStore/FeedbackStore, 只升级不重写
7. **测试**: 569 现有测试必须全绿, 新增按 §8 验收标准写测试
