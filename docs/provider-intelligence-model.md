# Provider Intelligence Model

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 日期: 2026-08-06 | 关联: ADR-0025, Phase 8B-3

## Provider Intelligence Loop

```
Provider (声明能力 + 成本)
    ↓
Execution (真实执行)
    ↓
Usage (自动记录: tokens/成本/时长/成功)
    ↓
Performance (聚合: 成功率/失败率/平均时长/总成本)
    ↓
Human Feedback (rating/approved/comment)
    ↓
Better Recommendation (三分数: capability + cost + performance)
    ↓
(回到 Provider 选择 — 但只推荐, 不自动切换)
```

## 核心区分

```
Declared Capability    CapabilityProfile (模型声明: matrix 质量分 + evidence)
Actual Performance     从 usage 聚合 (成功率先合并/时长加权)
declared_vs_actual()   gap = declared − actual (正=不及声明, 负=优于声明)
```

## 三分数推荐

```
RecommendationScore = 0.4·capability_score + 0.3·cost_score + 0.3·performance_score
无 usage 数据 → performance_score = 0.5 (中性, 8B-2 兼容)
只推荐, 禁止自动切换 (Human Approval 理念)
```

## 事件流

```
provider.selected → provider.execution.started → completed|failed → provider.usage.recorded
provider.feedback.created (人工反馈, UI 未来)
```

## 数据边界

```
UsageStore:   .factory/providers/usage.json
FeedbackStore:.factory/providers/feedback.json
估算成本 (非真实计费); 不实现支付; 不绑定 OpenAI/Claude API
```
