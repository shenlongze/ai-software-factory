# S28 Gap Analysis — Production Quality Recovery & Verification Closure

> 日期: 2026-08-29 | HEAD: 538e39f6 (v1.1.334)

## CAPABILITY_MATRIX Audit (S27)
- Production Experiment Reliability = REAL
- Optimization Effectiveness = NOT_YET_PROVEN (4 samples VERIFICATION_FAILURE)

## S26/S27 Failure Analysis (真实 evidence)
- S26: 4 真实 LLM samples 全 VERIFICATION_FAILURE (conf=1.0, "内置 pytest 失败")
- S27 分类正确 → 但**失败后无 Recovery 闭环** (样本直接 FAILED)

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| execute_production_run repair_fn + max_attempts (S12 repair loop) | production_run.py:364-365 | REAL 但**未被真实 LLM 链使用** |
| build_developer_repair_fn (codex 修复: failed artifact + pytest evidence) | professional_workflow.py:279 | REAL |
| S20 _run_verification (真实 syntax + pytest subprocess) | release_service.py:299 | REAL |
| S27 Failure Classification | experiment_reliability.py | REAL |
| Governance (S17) | governance_service.py | REAL |

## GAP (S28 新增)
| GAP | 最小实现 |
|-----|---------|
| Recovery Service: verification failure → 分类 → repair_fn → re-production → re-verification → RECOVERED/FAILED/EXHAUSTED/BLOCKED | recovery_service.py |
| Recovery Attempt Contract (attempt_id/run_id/classification/attempt_number/status/evidence_refs) | recovery_service.py |
| Recovery Policy (bounded retry: max_attempts=3; VERIFICATION_FAILURE 可 repair; AGENT/GOV 不可自动) | recovery_service.py |
| Verification Closure (新 artifact + 新 verification_id + PASS 才 RECOVERED; 禁复用旧 verification) | recovery_service.py |
| 历史 append-only (attempt-1 FAIL 保留, 不覆盖) | recovery_service.py |
| Idempotency/Concurrency/Restart (同 failure 不重复 recovery; flock) | recovery_service.py |
| CLI/API | cli_factory + fastapi_adapter |

## 设计
```
Verification Failure → S27 Classification → Recovery Policy (bounded, governance)
→ repair_fn (真实 failed artifact + pytest evidence) → re-production → new artifact
→ new verification → PASS → RECOVERED; FAIL → retry ≤3; 超限 → EXHAUSTED; 被阻 → BLOCKED
```

## 禁止
- Repair 修改 verification/release/health/approval 事实;直接写 workspace;无限 retry;LLM 自评 RECOVERED;伪造 PASS
