# Learning Contract & Lifecycle (S37)

> 日期: 2026-08-29 | 冻结于 S37

## 1. Lifecycle (冻结)
```
OBSERVED → HYPOTHESIS → CANDIDATE → EVALUATING → VALIDATED
                                           → REJECTED
                                           → SUPERSEDED
VALIDATED ≠ Production Active (真正进入 = S38 Promotion)
状态迁移: audit + lineage
```

## 2. Learning Scope (冻结)
```
node / agent / workforce / plugin / project / organization
Scope = Query Dimension (非继承树)
不同 Node 可产生不同 Candidate; 仅 same pattern + compatible scope + sufficient evidence
  → Shared Candidate
```

## 3. Learning Conflict (冻结)
```
Candidate A: X works vs Candidate B: X fails
→ Evidence/Scope/Freshness/Confidence 参与判断
→ 无法解决 → CONFLICT/UNRESOLVED (诚实, 非 last-write-wins)
```

## 4. Learning → Memory (冻结)
```
LearningCandidate → MemoryCandidate (仅 Governance 满足时)
LearningCandidate ≠ Memory (不自动永久记忆)
```

## 5. Learning Lineage (冻结)
```
LearningResult → Experience → Evidence → ProductionRun/NodeRun
每结果回答: 来源/NodeRun/Evidence/ContextFeedback/推理/Plugin/版本/时间
```

## 6. Learning Quality (冻结)
```
learning_candidates / validated / rejected / conflicted / unknown /
evidence_per_candidate; 数据不足 → NOT_AVAILABLE (不伪造)
```

## 7. Learning Cost (冻结)
```
input_tokens / output_tokens / estimated_cost / evidence_count / processing_time
cost_type = estimated (不伪装真实 billing)
```
