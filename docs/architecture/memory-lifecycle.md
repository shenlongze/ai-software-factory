# Memory Lifecycle & Conflict — Contract (S36)

> 日期: 2026-08-29 | 冻结于 S36

## 1. Memory Lifecycle (冻结)
```
CANDIDATE → ACTIVE → SUPERSEDED → RETIRED
状态变化: Audit + Lineage 保留; 不删除历史
SUPERSEDED: 被新 Evidence 推翻 (superseded_by 指向新 entry)
RETIRED: 显式废弃
```

## 2. Memory Freshness (冻结)
```
created_at / updated_at / valid_from / valid_until / version / confidence
valid_until 过期 → 不自动进 Context (freshness=0)
```

## 3. Memory Conflict (冻结)
```
同 scope + 同主题 (topic_key) 存在相矛盾 content → CONFLICT
解决: evidence_strength > confidence > freshness 参与
无法解决 → Conflict unresolved (诚实保持, 不 last-write-wins)
```

## 4. Evidence-aware Memory (冻结)
```
Memory → Experience → Evidence → ProductionRun/NodeRun
memory.confidence 从真实 evidence 投影 (不伪造)
```
