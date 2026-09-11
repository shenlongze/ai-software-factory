# 04 — EXPERIENCE TRUTH STATUS (CLOSURE AUDIT, 2026-09-06)

| 项 | Reality |
|---|---|
| exp-* 数量 | 84 (真实, memory/experience_store.json) |
| source 分布 | execution_records 55 / repair_task 18 / replanning 3 / validation 3 / gap 2 |
| EXS 来源 | 55 条真来自 exec/execution_records.json (P0 EXS) — extraction 桥真实 |
| **结构化 FK** | run FK: 0 | ver FK: 0 | release FK: 0 | task 字段: 79 (字符串) |
| 产生触发 | AutoLearner (M3 orchestrator 生产后) — P0/P1/P2-A 链无自动触发 |
| P2-A RELEASE→EXP | **0** (release 不产 experience; contract P2-C future) |

## 判定: M3 (真实数据, 提取桥真) 但缺 canonical FK → P2-C 目标
- exp 无法从 production_run_id/verification_id/release_id 反查 (只有字符串 source/task)
