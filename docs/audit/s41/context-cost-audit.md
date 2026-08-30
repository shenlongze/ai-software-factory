# S41 Context & Cost Audit

> 日期: 2026-08-29 | 纯审计

## Context Budget (S35/S36)
| Budget | 默认 | 状态 |
|--------|------|------|
| max_input_tokens | 8192 | REAL |
| max_memory_tokens | 2048 | REAL |
| max_artifact_tokens | 2048 | REAL |
| max_history_tokens | 1024 | REAL |
| max_tool_tokens | 1024 | REAL |
| max_output_tokens | 2048 | REAL |
| max_total_cost | 0.01 | REAL (estimated) |

## Context Explosion 检查
- JIT: ✅ 只取 requested scopes (S36 test_budget_selection)
- Utility ranking: ✅ 每 token 价值 (S36 context_utility)
- Progressive: ✅ 总 cost <= max_total (S36)
- 无继承: ✅ scope 非继承树 (S35)

## Cost 架构
| 维度 | 状态 | 证据 |
|------|------|------|
| Context cost | REAL (estimated) | S35 estimate_cost |
| Experiment budget | REAL (max_runs/max_cost → STOP) | S38 |
| Optimization budget | REAL (max_* → STOP) | S40 |
| Healing budget | REAL (max_attempts/max_cost) | S39 |
| 真实 provider billing | NOT_AVAILABLE (诚实) | cost_type=estimated |

## 结论
Node Independence 与 Context Efficiency 兼容 (JIT + Budget + Scope 非继承)。
Verified Outcome per Unit Cost = 目标, 基础设施 REAL。
