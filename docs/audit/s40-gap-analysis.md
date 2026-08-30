# S40 Gap Analysis — Governed Self-Optimization

> 日期: 2026-08-29 | HEAD: 90ebbeef (v1.1.346)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| Performance-aware Selection (S33) | performance_selection.py (plugin_performance/rank/select) | REUSE (Provider 优化基础) |
| Evaluation/Experiment/Governance/Canary/Promotion (S38) | promotion_service.py | REUSE |
| Rollback (S21/S39) | rollback_service.py / self_healing ROLLED_BACK | REUSE |
| Learning (S37) | learning_engine_v2.py | REUSE (Optimization Evidence → Observation) |
| Context Budget (S35/S36) | context_runtime.py / context_intelligence.py | REUSE |
| **OptimizationOpportunity** (evidence-driven, 非 LLM) | 无 | MISSING |
| **OptimizationCandidate** (Proposal; multi-candidate) | 无 | MISSING |
| **Optimization Strategy Plugin** (type=optimization) | 无 | MISSING |
| Baseline vs Candidate Comparison (outcome/cost/risk) | 无统一 | MISSING |
| **NO_CHANGE** 合法结果 | 无 | MISSING |
| **Anti-Thrashing** (cooldown/min_improvement/max_changes) | 无 | MISSING |
| **Optimization Budget** (max_experiments/max_cost/max_candidates/max_promotions) | 无 | MISSING |
| OptimizationDecision (可解释 reason) | 无 | MISSING |

## 设计
```
Production Evidence → OptimizationOpportunity (metric/current_value/expected_improvement/risk)
→ OptimizationCandidate(s) (multi: B/C/D; Proposal 非 Change; strategy_plugin_id)
→ Evaluation (baseline vs candidate: outcome/verification/recovery/cost/latency/risk)
→ Experiment (N runs, controlled) → Comparison (delta_*)
→ OptimizationDecision: PROMOTE / REJECT / NO_CHANGE (可解释 reason)
→ Governance (risk → human gate) → Canary (bounded) → Promotion (S38 复用)
→ New Evidence → S37 Observation
Anti-Thrashing: cooldown/min_improvement/max_changes_per_period (防 A→B→A→B)
Budget: max_experiments/max_cost/max_duration/max_candidates/max_promotions → STOP
首选 Plugin: Provider/Model Optimization (S33 performance selection 自然延伸)
24 Invariants: Plugin 化 / Core 不实现优化 / 无 Super Optimizer / 复用 S38 引擎
```

## 复用
S33 selection + S38 promotion + S21/S39 rollback + S37 learning + S35/S36 context

## 禁止
- 第二套 Evaluation/Experiment/Governance/Canary/Promotion/Rollback/Evidence
- Super Optimizer / LLM says should optimize / 无限震荡 / 无界成本
- local issue → global optimization / Performance 覆盖 Governance
