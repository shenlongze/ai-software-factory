# 08 — REAL DATA MATRIX (CLOSURE AUDIT, 2026-09-06)

| Entity | Count | 真实生产 | 测试 | Legacy | Canonical | Consumer |
|---|---|---|---|---|---|---|
| IDEA-* | 0 (E2E tmp) | 0 | 测试 | 0 | ✓ | product_truth |
| DISC-*/REQ-*/PRD-*/PLAN-* | 0 真实 | 0 | 测试 | — | ✓ | ✓ (P1 E2E) |
| TASK-* | ~250 (backlog) | ✓ | mix | 部分 | ✓ | P0 |
| run-* | E2E only | 0 | 测试 | — | ✓ | P0 |
| EXS-* | 100 (execution_records) | ✓ 历史 | mix | 部分 M3 | ✓ | P0 + extraction |
| art-*/ver-*/EVD-* | E2E only | 0 | 测试 | — | ✓ | P0 + release gate |
| RELEASE-* | 0 真实 (E2E tmp) | 0 | 测试 | — | ✓ | (无下游) |
| Experience | 84 | ✓ (55 EXS) | 部分 | — | store 真 | **无 FK 消费** |
| Observation/Candidate/Promotion | 0 | 0 | 0 | — | 代码 | — |
| AgentProfile | 0 | 0 | 0 | — | 代码 | — |
| learning_trace | 840 | ✓ 历史审计 | mix | — | trace | 审计展示 |

注: ~/.factory 真实数据 (P0/P1/P2-A canonical E2E 均在隔离 tmp, 未污染真实库)。
