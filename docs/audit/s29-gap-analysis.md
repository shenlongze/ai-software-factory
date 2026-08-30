# S29 Gap Analysis — Production Optimization Effectiveness & Controlled Workforce Experiment

> 日期: 2026-08-29 | HEAD: 6f7d300c (v1.1.335)

## CAPABILITY_MATRIX Audit (S28)
| 能力 | Status |
|------|--------|
| Optimization Infrastructure (S24) | REAL |
| Adaptive Workforce Variant (S25) | REAL |
| Real LLM Experiment (S26) | REAL (INCONCLUSIVE) |
| Experiment Reliability / Classification (S27) | REAL |
| Production Recovery (S28) | REAL (Real LLM Recovery PROVEN) |
| **Optimization Effectiveness** | **NOT_YET_PROVEN** |

## GAP Audit 表
| Capability | Current Reality | Gap | Risk | Reuse |
|-----------|----------------|-----|------|-------|
| Recovery-aware sample semantics (initial/final/recovery) | S26 sample 无 | 缺: initial_outcome/recovery_attempts/final_outcome/time_to_recovery | recovery 后样本无法正确计量 | 需新增 |
| Experiment Population Contract (完整 denominator) | S27 reliability 有 basic denominator | 缺: initial/final/recovered/unrecovered 分层 | 无法区分 initial vs final performance | 扩展 |
| Recovery-aware Comparison | S26 compare 只有 delta | 缺: initial_success/final_success/recovery_rate/mean_attempts | 无法判断 recovery 成本差异 | 需新增 |
| PROVEN Gate (12 条件) | S26 有部分 (min_sample/eval) | 缺: frozen/integrity/evidence-resolve 全条件 | 可能错误 PROVEN | 需新增 |
| Recovery 集成进 Experiment | S28 recovery_service 独立 | 缺: experiment sample → recovery 自动接线 | sample 失败后无 recovery 记录 | 接线 |

## 设计
```
Experiment (frozen hypothesis/metric/threshold/min_sample)
→ Governance → Control/Treatment Variant → Real ProductionRun ×N
→ Verification → FAIL? → Recovery (S28) → Re-Verification
→ Evaluation → Eligibility → Population Contract (initial/final/recovered)
→ Recovery-aware Comparison → PROVEN Gate → Outcome
```

## 禁止
- 改 threshold/hypothesis/metric 制造成功 / 删失败样本 / recovery 后删 initial failure / fake delta
