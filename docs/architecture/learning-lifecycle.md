# Learning Lifecycle 状态机 (S37)

> 日期: 2026-08-29 | 冻结于 S37

## 状态机
```
OBSERVED → HYPOTHESIS → CANDIDATE → EVALUATING → VALIDATED
                                          ↘ REJECTED
                                          ↘ SUPERSEDED
```

## 合法迁移
| From | To |
|------|-----|
| OBSERVED | HYPOTHESIS, REJECTED |
| HYPOTHESIS | CANDIDATE, REJECTED |
| CANDIDATE | EVALUATING, REJECTED, SUPERSEDED |
| EVALUATING | VALIDATED, REJECTED, SUPERSEDED |
| VALIDATED | SUPERSEDED |
| REJECTED | (终态) |

非法迁移拒绝; history append-only; audit。

## 核心语义
- VALIDATED ≠ Production Active (S38 Promotion 才改变生产)
- SUPERSEDED: 被更强 evidence 覆盖 (保留历史)
- 任何状态变化: audit + lineage
