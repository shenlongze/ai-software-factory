# S26 Real LLM Experiment Evidence

> 日期: 2026-08-29 | 实验: 真实 deepseek LLM, 2+2 样本 | 成本: 4 次真实 LLM 调用

## Hypothesis
```
reviewer 加入后改善生产质量
metric = overall_score (S13 Evaluation)
direction = HIGHER_IS_BETTER
control = developer
treatment = developer + reviewer
min_sample = 2, threshold = 0.0
```

## Experiment
```
experiment_id: exp-<uuid>
Governance: APPROVED (human)
Control runs: 2 (software_developer 真实 LLM)
Treatment runs: 2 (software_developer + reviewer 真实 LLM)
```

## Real LLM: YES (deepseek provider, 真实 llm_gateway)

## Production Evidence (诚实, 含失败样本不筛选)
```
samples:
  control#1:  eligible=False, reason=INCOMPLETE (真实 LLM 输出未通过内置 pytest)
  treatment#1: eligible=False, reason=INCOMPLETE
  control#2:  eligible=False, reason=INCOMPLETE
  treatment#2: eligible=False, reason=INCOMPLETE
```

## Control Result: 无 ELIGIBLE 样本 (真实失败)
## Treatment Result: 无 ELIGIBLE 样本 (真实失败)

## Outcome: **INCONCLUSIVE**
## Effectiveness: **NOT_YET_PROVEN**

## Reason
真实 LLM 生产链路: LLM 输出代码 → 内置 pytest 验证 → 全部失败(INCOMPLETE)。
这是真实 Production Evidence(不伪造成功): 单 developer 节点的 LLM 生产无法稳定产出
通过 pytest 的代码 → eligible 样本 = 0 → 无法比较 control vs treatment。

## 结论
- Real LLM Experiment Infrastructure = REAL (真实 provider 调用 + 真实失败记录)
- Optimization Effectiveness = NOT_YET_PROVEN (诚实)
- 下一步: 完整 professional workflow (PM→Arch→Dev→QA 链, S11 已验证) 下重跑,
  或提高 LLM 输出容错 (S12 Repair 复用)
