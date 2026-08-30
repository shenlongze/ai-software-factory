# S41 Capability GAP Classification

> 日期: 2026-08-29 | 纯审计

## GAP 分类
| # | GAP | 分类 | 优先级 |
|---|-----|------|:---:|
| 1 | Plugin type 白名单需扩展 (开放注册) | P1 OS Core 改进 | DEFER |
| 2 | Learning/Healing/Optimization 统一 Strategy Contract | P2 架构建议 | DEFER |
| 3 | 并行 DAG 执行 (S3 串行) | P2 Production | DEFER |
| 4 | 真实 provider billing 数据 | P4 Optimization | DEFER |
| 5 | Enterprise 模块 (Market/Sales/Finance/HR) | FUTURE | REJECT (App 层) |
| 6 | 前端完整 Control Tower UI (S22 卡片级) | P3 Product/UX | DEFER |
| 7 | 真实 LLM Optimization E2E (S40 用 deterministic fixture) | P2 证据补强 | NEXT |
| 8 | 全量零桩清理 (旧 14K 死代码) | P4 | DEFER |

## 原则
- 不把全部 GAP 列为 TODO;只列有明确价值 + 符合架构方向
- P0 (Architecture Risk): **无**
- 最重要: GAP #7 (真实 LLM 优化实验证据) — 与 S24-S29 的 Effectiveness=NOT_YET_PROVEN 一致
