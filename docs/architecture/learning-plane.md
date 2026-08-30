# Learning Plane — Contract (S37)

> 日期: 2026-08-29 | 冻结于 S37

## 1. 核心闭环 (冻结)
```
Production Evidence → LearningObservation → LearningHypothesis
→ LearningCandidate → Evidence Evaluation → VALIDATED/REJECTED/CONFLICT → [STOP]
Promotion (改 Production) = S38, S37 绝不自动
```

## 2. LearningObservation (冻结)
```
observation_id / source_type(production_run|node_run|verification|recovery|
  evaluation|context_feedback|experience|performance) / source_id /
scope / pattern_key / outcome(SUCCESS|FAILURE|UNKNOWN) / detail / evidence_refs[] / created_at
来源必须是 Production Evidence (禁 Conversation/LLM imagination)
```

## 3. LearningHypothesis (冻结)
```
hypothesis_id / observation_ids[] / statement / status(HYPOTHESIS) / scope
Hypothesis ≠ Fact
```

## 4. LearningCandidate (冻结)
```
candidate_id / hypothesis_id / type(STRATEGY|PATTERN|LESSON|PROCEDURE|
  CONSTRAINT|SUCCESS_PATTERN|FAILURE_PATTERN) / scope / content /
aggregate(sample_count/success_count/failure_count/verification_count/
  recovery_count/confidence) / lifecycle / evidence_refs[]
```

## 5. Confidence (冻结)
```
observed < inferred < validated (小样本自然降权)
1 次成功 ≠ 高置信度 (样本加权)
```

## 6. Negative Learning (冻结)
```
Failure Pattern: what fails / why / under which scope
Strategy A 成功 2 失败 8 → 保存完整 (不只 "A worked")
```
