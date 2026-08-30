# S26 Architecture Proposal — Real LLM Optimization Experiment & Effectiveness Proof

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. OptimizationHypothesis (冻结, 结构化)
```
hypothesis_id / optimization_id / statement / metric / direction(HIGHER_IS_BETTER|LOWER_IS_BETTER) /
control_definition / treatment_definition / baseline_reference / minimum_sample_size /
success_threshold / risk / created_at
Metric 与 threshold 在实验创建时冻结, 结果后不可改
```

## 2. Real LLM Experiment (冻结)
```
control: Developer (真实 LLM executor)
treatment: Developer + Reviewer (真实 LLM + 额外验证节点)
经 S25 WorkforceVariant → run_with_variant(base_factory=build_real_executor_factory)
→ 真实 ProductionRun → S13 Evaluation → Metric
```

## 3. Budget Guard (冻结)
```
max_control_runs / max_treatment_runs / max_total_runs (默认 2+2+4)
超限 → STOPPED/INCONCLUSIVE (不无限调用 LLM)
```

## 4. Sample Eligibility (冻结)
```
ELIGIBLE: ProductionRun COMPLETED + Evaluation 存在 + metric 存在
INELIGIBLE: 条件不满足 (记录原因, 不静默丢弃 → 防 selection bias)
FAILED: ProductionRun 失败
```

## 5. PROVEN 硬性保护 (冻结)
```
PROVEN 仅当: sample ≥ minimum_sample_size + 全 evidence_refs + Evaluation + metric +
  Control/Treatment 隔离 + delta 达 threshold + 方向正确
否则 → IMPROVED 不可声明 (只能 NOT_PROVEN/INCONCLUSIVE)
```

## 6. Outcome (冻结)
```
IMPROVED / REGRESSED / UNCHANGED / INCONCLUSIVE
+ Effectiveness: PROVEN / REJECTED / NOT_YET_PROVEN (三态独立)
```

## 7. 复用
S24 Baseline/Measurement/Outcome + S25 Variant/Assignment + S11 真实 LLM + S13 Evaluation + S17 Governance

## 8. CLI/API
```
factory optimization experiment create/approve/run/status/compare/outcome/lineage
POST /api/optimization/experiments/{id}/llm-run (带真实 LLM executor)
```
