# S29 Real E2E Evidence — Recovery-aware Effectiveness Experiment

> 日期: 2026-08-29 | 真实 LLM (deepseek) + codex repair | 证据: /tmp/s29-real-e2e-evidence.json

## 实验
```
Hypothesis: reviewer 加入改善 final_success_rate
Frozen contract: metric=final_success_rate, direction=HIGHER_IS_BETTER, threshold=0.0, min_sample=2
Control: developer (真实 LLM)
Treatment: developer + reviewer (真实 LLM)
Budget: 2+2+4
Governance: APPROVED
```

## 真实样本
| sample | initial | recovery | final | eligible |
|--------|---------|----------|-------|----------|
| control#1 | PASS | 0 | PASS | True |
| control#2 | PASS | 0 | PASS | True |
| treatment#1 | PASS | 0 | PASS | True |
| treatment#2 | PASS | 0 | PASS | True |

## Population (完整 denominator)
```
total: 4, completed: 4, failed: 0, recovered: 0, unrecovered: 0, eligible: 4, ineligible: 0
```

## Comparison (Recovery-aware)
```
final_success_rate: control=1.0 treatment=1.0 delta=0.0 (0.0%)
initial_success_rate: control=1.0 treatment=1.0
recovery_rate: N/A (无失败)
```

## Outcome
```
UNCHANGED | effectiveness: NOT_YET_PROVEN
```

## 结论
- 真实 LLM Production + Verification + Evaluation + Recovery-aware 全链真实执行
- 本次实验 control 与 treatment **无差异** → 诚实 UNCHANGED (不伪造 IMPROVED)
- 与 S26 不同: 本次任务("写 add 函数")简单, 真实 LLM 全部通过 pytest (无 recovery 触发)
- PROVEN Gate 生效: 即使无差异也诚实 NOT_YET_PROVEN
