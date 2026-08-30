# S24 Architecture Proposal — Workforce Optimization & Production Optimization

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Contract (冻结)
```
OptimizationAnalysis: analysis_id/project_id/scope/status(REQUESTED/ANALYZING/COMPLETED/FAILED)/
  signals[]/patterns[]/candidates[]/evidence_refs[]
OptimizationHypothesis: hypothesis_id/analysis_id/target/problem/proposed_change/expected_effect/
  risk/confidence/evidence_refs/status — confidence ≠ improvement (仅 evidence 支持度)
Baseline: baseline_id/scope/metric_definitions/sample_size/measurement_window/
  production_run_refs[]/metrics/evidence_refs/status(COMPLETED/BASELINE_INSUFFICIENT)
Experiment: experiment_id/hypothesis_id/baseline_id/control_definition/treatment_definition/
  status(PROPOSED/APPROVAL_REQUIRED/APPROVED/RUNNING/COMPLETED/FAILED/REJECTED/INCONCLUSIVE)/
  governance/created_at
Measurement: measurement_id/experiment_id/metric/control_value/treatment_value/delta/delta_percent/
  sample_size/evidence_refs
Comparison: result(IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE)/delta/evidence
OptimizationOutcome: outcome_id/experiment_id/result/metrics/evidence_refs/decision/reason
```

## 2. 反虚假规则 (冻结)
- 无真实 Baseline → BASELINE_INSUFFICIENT
- 无真实 Experiment → EXPERIMENT_INSUFFICIENT
- Control/Treatment 不可比 → INCONCLUSIVE
- 样本太少 → INCONCLUSIVE
- 仅 LLM 声称 → REJECT

## 3. Metrics (冻结, 机器可测)
repair_count / execution_duration / failure_rate / verification_failure_rate / rollback_count / success_rate
(来自真实 production runs + S13 evaluation)

## 4. Governance
Experiment Proposal → Governance Approval (human) → 才可 RUNNING
(复用 S17; experiment 不绕过)

## 5. Experience Integration
仅 IMPROVED (真实实验+测量+outcome) → Optimization Experience
PROPOSED/INCONCLUSIVE/REJECTED → 不伪装成功

## 6. CLI/API
```
factory optimization analyze/hypotheses/baseline/experiment/run/compare/outcome/explain
POST /api/optimization/analyze | GET /api/optimization/analyses/{id}
GET /api/optimization/hypotheses | POST /api/optimization/baselines
POST /api/optimization/experiments | POST /api/optimization/experiments/{id}/run
GET /api/optimization/experiments/{id}/compare | /outcome
```
