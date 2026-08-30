# S38 Gap Analysis — Learning Evaluation & Governed Promotion

> 日期: 2026-08-29 | HEAD: 501cd431 (v1.1.344)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| Experiment (S24-S29) | effectiveness_service.py / llm_experiment_service.py (baseline/candidate/hypothesis/budget) | REUSE |
| Rollback (S21) | rollback_service.py (health→incident→policy→rollback→verify) | REUSE (Canary 回滚) |
| Governance (S17) | governance_service.py (request_approval/decide_approval/expiration) | REUSE (Promotion Gate) |
| Learning (S37) | learning_engine_v2.py (candidates VALIDATED) | REUSE (Promotion 输入) |
| Performance (S33) | performance_selection.py | REUSE (baseline/candidate metric) |
| **统一 Promotion Contract** | 无 (Candidate→Evaluation→Experiment→Comparison→Governance→Canary→Promotion) | MISSING |
| Evaluation (baseline vs candidate, evidence-based) | 无统一 | MISSING |
| Comparison (IMPROVED/REGRESSED/INCONCLUSIVE/CONFLICT) | 无 | MISSING |
| Risk Classification (LOW/MEDIUM/HIGH/CRITICAL) | 无 | MISSING |
| Canary (scope/runs/cost/duration; regression→rollback) | 无 | MISSING |
| Promotion Lifecycle + Snapshot (immutable) | 无 | MISSING |
| Promotion Policy Plugin (替换测试) | 无 | MISSING |
| Cost-aware Evaluation | 无 (cost 一级) | MISSING |

## 设计
```
LearningCandidate (VALIDATED) → PromotionCandidate
→ Evaluation (baseline vs candidate; success/verification/recovery/quality/cost/latency)
→ Experiment (budget/sample/sandbox/replay; max_runs/max_cost)
→ Comparison (delta_* → IMPROVED/REGRESSED/INCONCLUSIVE/CONFLICT)
→ Governance (AUTO_APPROVE/REVIEW_REQUIRED/HUMAN_APPROVAL_REQUIRED/REJECT; 风险分类)
→ Canary (scope/runs/cost; regression → 复用 S21 rollback)
→ PromotionDecision + PromotionSnapshot (immutable)
Lifecycle: CANDIDATE→EVALUATING→EVALUATED→GOVERNED→CANARY→PROMOTED; 失败→REJECTED/INCONCLUSIVE/ROLLED_BACK
Plugin: Evaluator/Experimenter/Promotion Policy (Core 零修改替换)
```

## 复用
S21 rollback + S17 governance + S29 effectiveness + S33 performance + S37 learning

## 禁止
- LLM→Production / Learning→Production / Evaluation PASS→无限自动
- 第二套 Rollback / 第二套 Experiment / 隐藏控制面
- 无证据 PASS / 无 Human Gate 的高风险 Promotion / 无限实验
