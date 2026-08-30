# Evaluation Contract (S38)

> 日期: 2026-08-29 | 冻结于 S38

## 1. PromotionCandidate (冻结)
```
promotion_candidate_id / learning_candidate_id (S37 输入) / target(memory|skill|strategy|plugin_version|workflow) /
baseline_ref / candidate_ref (plugin/version/skill/workforce 可追溯) / scope / risk / created_at
```

## 2. EvaluationRun (冻结)
```
evaluation_run_id / promotion_candidate_id / dimensions(success|verification|recovery|quality|cost|latency|context_efficiency) /
baseline_metrics / candidate_metrics / sample_count / confidence / evidence_refs[] / cost_type(estimated)
禁止: LLM says better 作为唯一证据
```

## 3. Baseline (冻结)
```
Baseline ≠ Candidate; 两者可追溯到 Plugin/Version/Skill/Agent/Workforce/Context Strategy
Historical Evidence immutable (Replay 不修改历史)
```

## 4. Cost (冻结, 一级)
```
input_tokens / output_tokens / context_tokens / execution_cost / evaluation_cost / latency
cost_type = estimated (不伪造 billing)
比较: quality / cost (Maximize verified outcome per unit cost)
```
