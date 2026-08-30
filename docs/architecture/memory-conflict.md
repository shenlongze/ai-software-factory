# Memory Conflict — Contract (S36)

> 日期: 2026-08-29 | 冻结于 S36

## 1. Conflict Detection (冻结)
```
同 scope + 同 topic_key + 语义矛盾 → CONFLICT
topic_key = 规范化主题 (content 首词/哈希, v1 确定性)
```

## 2. Conflict Resolution (冻结)
```
优先级: evidence_strength > confidence > freshness > scope
可自动解决 → 高 evidence 胜出 (低者 → SUPERSEDED)
不可解决 → status = CONFLICT_UNRESOLVED (诚实)
禁止: last-write-wins
```

## 3. 记录 (冻结)
```
conflict_id / topic_key / scope / memory_ids[] / status(RESOLVED|UNRESOLVED) /
resolution(winner_memory_id) / created_at
```
