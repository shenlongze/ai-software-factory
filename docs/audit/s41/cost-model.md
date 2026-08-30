# S41 Cost Model

> 日期: 2026-08-29 | 纯审计

## Cost 维度
| 维度 | 记录 | Budget | 状态 |
|------|------|:---:|------|
| LLM | estimated (token/4) | max_total_cost | REAL |
| Context | requested/selected/compressed/rejected tokens | S35 budget | REAL |
| Memory | retrieval cost (estimated) | max_memory_tokens | REAL |
| Tool | executor cost (estimated) | experiment budget | REAL |
| Execution | run cost | - | REAL |
| Verification | subprocess (本地) | - | 免费 |
| Experiment | max_runs/max_cost | STOP | REAL |
| Healing | max_attempts/max_cost | STOP | REAL |
| Optimization | max_experiments/max_cost | STOP | REAL |

## 核心指标
> Verified Outcome per Unit Cost
- 基础设施 REAL (S36 context utility + S38 experiment budget + S40 optimization budget)
- 数据: 真实 provider billing NOT_AVAILABLE (cost_type=estimated 诚实)

## 结论
Cost 是一级指标;所有 Intelligence 操作有 budget + STOP;无无限成本路径。
