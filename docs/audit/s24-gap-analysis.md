# S24 Gap Analysis — Workforce Optimization & Production Optimization

> 日期: 2026-08-29 | HEAD: c524c345 (v1.1.330)

## CAPABILITY_MATRIX Audit
- 无 Optimization/Experiment/Baseline 条目 → S24 新增
- S1-S23 能力(Production Kernel/Governance/Release/Rollback/Health/Intelligence)全 REAL

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| 生产指标来源: repair_count/attempt_count/evaluation_score | production_evaluation.py (S13) | REAL |
| S23 Intelligence (signals/candidates/evidence_refs) | production_intelligence.py | REAL |
| S14/S15 Experience (extract/retrieve/lineage) | production_experience.py | REAL |
| Governance (approval) | governance_service.py (S17) | REAL |
| Production Kernel (run/verify/release/rollback) | S11-S22 | REAL |

## MISSING (S24 新增)
| GAP | 最小实现 |
|-----|---------|
| OptimizationAnalysis (signals→patterns→candidates) | optimization_service.py |
| OptimizationHypothesis (target/problem/proposed_change/expected_effect/risk) | optimization_service.py |
| Baseline (真实 production runs 指标; BASELINE_INSUFFICIENT 正式结果) | optimization_service.py |
| Experiment (control/treatment + governance approval) | optimization_service.py |
| Measurement (metric/control/treatment/delta/delta_percent/evidence_refs) | optimization_service.py |
| Comparison (IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE) | optimization_service.py |
| Outcome (decision + 真实实验证明; IMPROVED 才进 Experience) | optimization_service.py |
| CLI/API | cli_factory + fastapi_adapter |

## 设计
```
Production Facts (production runs/evaluation)
  → Optimization Signals (repair_count/duration/failure 等真实指标)
  → Analysis → Hypothesis (explain itself)
  → Baseline (真实 runs 度量; 不足 → BASELINE_INSUFFICIENT)
  → Experiment (control vs treatment, Governance approval)
  → Measurement (delta/delta_percent + evidence_refs)
  → Comparison → Outcome (IMPROVED/REGRESSED/UNCHANGED/INCONCLUSIVE)
  → IMPROVED 才 → Experience
```

## 禁止
- fake baseline / hard-coded improvement / LLM 宣称优化成功 / 绕过 Governance / 第二套 engine
