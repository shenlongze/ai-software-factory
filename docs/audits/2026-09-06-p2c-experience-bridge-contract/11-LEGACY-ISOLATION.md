# 11 — LEGACY ISOLATION (P2-C CONTRACT, 2026-09-06)

| 对象 | 分类 | 处置 |
|---|---|---|
| 84 条现有 exp (M3) | LEGACY-HISTORICAL | 保留原样; 不迁移不 backfill FK |
| M3 AutoLearner 提取 | LEGACY 路径 | 保留 (旧数据继续可学); 新 canonical 走 ExperienceBridge |
| learning_trace (840) | LEGACY 审计 | 保留; 新 bridge 事件可选写 (不必须) |
| 旧 execution_records 提取 | LEGACY | 保留 (历史 exp 来源); 新执行经 P0 finalize bridge |
| rel-* / M3 production_run | LEGACY | 隔离 (P2-A 已定) |

**禁止 migration/backfill** — 84 条保持历史; 新链第一天正确。
