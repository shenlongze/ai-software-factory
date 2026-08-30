# S27 Gap Analysis — Production Experiment Reliability & Evaluation Quality

> 日期: 2026-08-29 | HEAD: 98ce4381 (v1.1.333)

## CAPABILITY_MATRIX Audit (S26)
- Real LLM Experiment = REAL
- Optimization Effectiveness = NOT_YET_PROVEN (4 samples INCOMPLETE)

## S26 Failure Re-analysis (真实 evidence)
4 个真实 LLM samples 全部 reason=INCOMPLETE。从真实代码 evidence:
- software_developer executor 返回 `ok: False, error="内置 pytest 失败"` (professional_workflow.py:503)
- → ProductionRun state=FAILED
- → **根因 = VERIFICATION_FAILURE** (LLM 生成了代码, 但内置 pytest 验证失败)
- S26 只记 reason=INCOMPLETE → **丢失分类粒度** (S27 核心 GAP)

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| ProductionRun states (COMPLETED/FAILED/BLOCKED) | production_run.py:30 | REAL |
| Verification status (PASS/FAIL/INCONCLUSIVE/BLOCKED) | verification.py:17 | REAL |
| Evaluation (overall_score) | production_evaluation.py (S13) | REAL |
| LLM Experiment (S26) | llm_experiment_service.py | REAL |
| Evidence Model (S23, refs 校验) | production_intelligence.py | REAL |

## MISSING (S27 新增)
| GAP | 最小实现 |
|-----|---------|
| Failure Classification (Agent/Production/Verification/Evaluation/Infra/Budget/Timeout/Gov/UNKNOWN) | experiment_reliability.py |
| Production Outcome Contract (COMPLETED/INCOMPLETE/FAILED/BLOCKED/CANCELLED 投影) | experiment_reliability.py |
| Sample Eligibility 正式化 (ELIGIBLE/INELIGIBLE + reason/classification/evidence_refs) | experiment_reliability.py |
| Selection Bias 保护 (完整 denominator: total/eligible/ineligible/failed) | experiment_reliability.py |
| Evaluation Quality Contract (metric 有效/无效 → EVALUATION_INVALID) | experiment_reliability.py |
| Experiment Reliability 聚合 (失败分布) | experiment_reliability.py |
| CLI/API | cli_factory + fastapi_adapter |

## 设计
```
ProductionRun → Artifact → Verification → Evaluation (facts)
  → FailureClassification (deterministic projection, evidence_refs)
  → SampleEligibility (ELIGIBLE/INELIGIBLE + reason)
  → Experiment Reliability (完整 denominator, 防 selection bias)
Classification 是 Projection, 非新事实源
```

## 禁止
- 统一写 INCOMPLETE / LLM 生成事实结论 / 删除失败样本 / 伪造分类 / 改 metric 制造成功
