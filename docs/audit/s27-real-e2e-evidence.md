# S27 Real E2E Evidence — S26 Failure Re-analysis

> 日期: 2026-08-29 | 真实 LLM E2E (deepseek, 4 样本) | 证据: /tmp/s27-real-e2e-evidence.json

## S26 核心问题回答
> S26 的 4 个 INCOMPLETE 样本,到底是什么失败?

**Answer (evidence-backed): 4 个样本全部 = VERIFICATION_FAILURE (confidence 1.0)**

## 真实样本分类表
| sample | run | state | classification | confidence | evidence |
|--------|-----|-------|---------------|-----------|----------|
| control#1 | prun-81b528117e9a | FAILED | VERIFICATION_FAILURE | 1.0 | "Node software_developer FAILED: 内置 pytest 失败" |
| control#2 | prun-ff07c04bf827 | FAILED | VERIFICATION_FAILURE | 1.0 | 同上 |
| treatment#1 | prun-a1bf19035f62 | FAILED | VERIFICATION_FAILURE | 1.0 | 同上 |
| treatment#2 | prun-47285601886d | FAILED | VERIFICATION_FAILURE | 1.0 | 同上 |

## Reliability 聚合 (完整 denominator, 防 selection bias)
```
total_samples: 4
eligible_samples: 0
ineligible_samples: 4
failure_classification_distribution: {VERIFICATION_FAILURE: 4}
```

## Compare
```
INCONCLUSIVE | effectiveness: NOT_YET_PROVEN
```

## 结论
- S26 的 INCOMPLETE 不是 Agent 失败、不是基础设施失败、不是 Evaluation 失败
- 根因 = LLM 生成代码后内置 pytest 验证失败 (VERIFICATION_FAILURE)
- S27 分类器正确区分 (confidence 1.0 + 真实 failure evidence)
- 失败样本全部保留在 denominator (0 eligible 明确可见, 不伪装)
