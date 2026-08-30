# S29 Architecture Proposal + Contract — Optimization Effectiveness Experiment

> 日期: 2026-08-29 | 状态: CONTRACT FREEZE

## 1. Recovery-aware Sample Contract (冻结)
```
experiment_sample_id / experiment_id / arm(control|treatment) /
initial_production_run_id / initial_verification_id / initial_outcome(PASS|FAIL) /
recovery_attempts[] (S28) / final_production_run_id / final_verification_id /
final_outcome(PASS|FAIL) / time_to_recovery / artifact_history / evidence_refs
```

## 2. Population Contract (冻结)
```
total / assigned_control / assigned_treatment /
completed / failed / incomplete / blocked /
verified_pass / verified_fail / recovered / unrecovered /
evaluation_valid / evaluation_invalid / eligible / ineligible
初始 PASS 与 recovery 后 PASS 分开统计 (initial vs final)
```

## 3. Recovery-aware Comparison (冻结)
```
initial_success_rate (initial PASS / total)
final_success_rate (final PASS / total, 含 recovered)
recovery_rate (recovered / initial_fail)
mean_recovery_attempts
primary_metric: final_success_rate (有 Evaluation 支撑)
secondary: initial_success_rate, recovery_rate
```

## 4. PROVEN Gate (冻结, 12 条件全满足才 PROVEN)
```
1 hypothesis frozen 2 experiment approved 3 min_sample reached
4 eligible sufficient 5 evaluation valid 6 primary metric available
7 control measurement 8 treatment measurement 9 comparison valid
10 no integrity violation 11 evidence_refs resolvable 12 threshold satisfied
否则 → INCONCLUSIVE / NOT_YET_PROVEN
```

## 5. 复用
S24 experiment + S25 variant + S26 budget/eligibility + S27 classification + S28 recovery

## 6. CLI/API
```
factory experiment create/show/approve/run/samples/compare/outcome/evidence
POST /api/experiments | GET /api/experiments/{id} | POST /api/experiments/{id}/approve
POST /api/experiments/{id}/run | GET /api/experiments/{id}/samples
GET /api/experiments/{id}/compare | GET /api/experiments/{id}/outcome | GET /api/experiments/{id}/evidence
```
