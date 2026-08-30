# Context Utility — Contract (S36)

> 日期: 2026-08-29 | 冻结于 S36

## 1. 维度 (冻结)
```
relevance: purpose 关键词匹配度 (0-1)
evidence_strength: source_type=evidence→1.0, experience→0.8, manual→0.4
freshness: 30 天内→1.0, 90 天→0.6, 更久→0.3 (valid_until 过期→0)
confidence: MemoryEntry.confidence (0-1)
scope_match: 与请求 scope 完全匹配→1.0, 子集→0.6
token_cost: 归一化 token 数惩罚
```

## 2. Score (冻结)
```
utility = 0.4*relevance + 0.25*evidence + 0.15*freshness + 0.1*confidence + 0.1*scope_match - 0.05*cost_norm
可解释: 每条 candidate 输出各维度值
```

## 3. 选择 (冻结)
```
utility desc → 累计 budget → 最优组合
rejected candidates 记录 rejected_tokens + reason(overflow/utility_low)
```
