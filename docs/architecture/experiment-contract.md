# Experiment & Comparison Contract (S38)

> 日期: 2026-08-29 | 冻结于 S38

## 1. Experiment (冻结)
```
experiment_id / promotion_candidate_id / baseline / candidate / scope / sample_size /
budget(max_runs/max_tokens/max_cost/max_duration) / success_criteria / stop_conditions
Sandbox/Controlled Environment/Replay (复用现有); 若 Production Canary → 必须 Governance
超限 → STOP (不得无限实验)
```

## 2. ComparisonResult (冻结)
```
delta_success / delta_verification / delta_recovery / delta_quality / delta_cost / delta_latency
status: IMPROVED | REGRESSED | NO_SIGNIFICANT_CHANGE/INCONCLUSIVE | CONFLICT
证据不足 → INCONCLUSIVE (不能强行 PASS)
```

## 3. Deterministic 比较 (冻结)
```
evidence_count >= min_samples 才允许判断方向 (小样本 → INCONCLUSIVE)
Cost-aware: 同 quality 下 cost 低者胜 (quality/cost 比值参与)
```

## 4. Replay (冻结)
Historical Evidence → Replay → Baseline vs Candidate → Comparison; 历史 immutable。
