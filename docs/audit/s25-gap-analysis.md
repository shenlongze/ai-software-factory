# S25 Gap Analysis — Adaptive Workforce & Optimization Validation

> 日期: 2026-08-29 | HEAD: 024e16b4 (v1.1.331)

## CAPABILITY_MATRIX Audit (S24)
- Optimization Infrastructure = REAL (S24)
- Optimization Effectiveness = NOT YET PROVEN (S24 诚实声明)

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| executor_factory 注入点 (Production Run 真实执行差异入口) | production_run.py:360 | REAL |
| build_executor_factory / build_real_executor_factory (Workforce 变体基础) | professional_workflow.py:138/379 | REAL |
| Baseline/Experiment/Measurement/Comparison/Outcome | optimization_service.py (S24) | REAL |
| Governance approval (S17) | governance_service.py | REAL |
| Experience (S14/S15, 仅成功吸收) | production_experience.py | REAL |

## MISSING (S25 新增)
| GAP | 最小实现 |
|-----|---------|
| WorkforceVariant (真实可执行差异: 不同 executor_factory/节点集, 非字符串) | adaptive_workforce.py |
| Variant→ProductionRun 真实注入 (execute_production_run 用 variant factory) | adaptive_workforce.py |
| Experiment Assignment (run 绑定 experiment_id/variant_id/assignment_id) | adaptive_workforce.py |
| Governance 在 Variant Activation 前 (未批准 → run blocked) | adaptive_workforce.py |
| Proposal → Variant → Assignment → Run → Measurement → Outcome 全链 lineage | adaptive_workforce.py |
| CLI/API | cli_factory + fastapi_adapter |

## 设计
```
Optimization Proposal → Governance approval → WorkforceVariant (executor_factory 差异)
→ Assignment (run→variant) → ProductionRun (真实执行 control/treatment)
→ Evaluation → Measurement → Comparison → Outcome
control = developer only
treatment = developer + reviewer (额外验证节点) — 真实执行路径不同
```

## 禁止
- Variant 修改 Production Truth (artifact/verification/release/health)
- 未批准 Treatment 运行 / 第二套 engine / fake variant / hardcode IMPROVED
