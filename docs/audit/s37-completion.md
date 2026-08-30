# S37 Evidence-driven Workforce Learning — Completion Report

> 日期: 2026-08-29 | HEAD: (S37 commit) | v1.1.344

## 1. GAP Audit
Experience (S14/S15) REAL;旧 LearningEngine (会话时代) PARTIAL 无生产闭环;Observation/Hypothesis/Candidate/Evaluation 全 MISSING。

## 2. LearningObservation — REAL
来源白名单 (production_run/node_run/verification/recovery/evaluation/context_feedback/experience/performance);禁 conversation/LLM imagination (测试)。

## 3. LearningHypothesis — REAL
HYPOTHESIS ≠ Fact;observation_ids 关联。

## 4. LearningCandidate — REAL
7 类型 (STRATEGY/PATTERN/LESSON/PROCEDURE/CONSTRAINT/SUCCESS_PATTERN/FAILURE_PATTERN)。

## 5. Learning Lifecycle — REAL
OBSERVED→HYPOTHESIS→CANDIDATE→EVALUATING→VALIDATED/REJECTED/SUPERSEDED;非法迁移拒绝;history append-only。

## 6. Evidence Evaluation — REAL
样本不足 → EVALUATING (confidence=unknown, 不伪装);足够 → VALIDATED (validated);失败多 → REJECTED。

## 7. Negative Learning — REAL
Failure Pattern 完整保存 (what fails / why / scope; 成功 2 失败 8 全记录)。

## 8. ContextFeedback 消费 — REAL
S36 USEFUL/NOT_USEFUL/UNKNOWN → S37 Observation (source_type=context_feedback)。

## 9. Conflict — REAL
同 pattern VALIDATED vs REJECTED → CONFLICT (evidence 参与; 非 last-write-wins)。

## 10. Governance Boundary — REAL (最重要)
Learning [STOP at Candidate/Evaluation];**不修改 Production** (测试断言 runs 不变);不自动改 Skill/Plugin/Workflow/Policy/Core。

## 11. Learning Plugin — REAL
type=learning;替换不修改 Core;LLM proposes → Core validates (S37 deterministic discovery)。

## 12. Cost + Quality — REAL
cost_type=estimated;learning_candidates/validated/rejected/conflicted 真实。

## 13. CLI/API — REAL
factory learn 7 命令 + 5 API 端点 (openapi 271)。

## 14. Tests — 12
evidence-whitelist/lifecycle/small-sample/validated/negative-learning/run-learning/no-production-modification/conflict/context-feedback/plugin-replacement/CLI/API。

## 15. Regression
```
S37: 12/12 | 全量: 978 passed + 6 skipped (零失败) | Zero-Stub: PASS | 前端 tsc: PASS
```

## 16. Commits
feat: S37 Evidence-driven Workforce Learning + chore(版本): bump v1.1.344 + tag

## 17. Final Verdict
**S37 = PASS** — Evidence→Experience→Learning→Candidate→Evaluation→**[STOP]** 全链 REAL。**Evidence 是事实,Learning 是假设,Evaluation 是证明,Promotion 才是改变生产 (S38)**。按指令停止,不进入 S38。
