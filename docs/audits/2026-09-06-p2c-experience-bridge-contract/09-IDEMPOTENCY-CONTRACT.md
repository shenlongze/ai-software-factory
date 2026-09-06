# 09 — IDEMPOTENCY CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 唯一键: (source, source_id)

| source | source_id | 幂等保证 |
|---|---|---|
| execution | {run_id}:{exs_id} | 同 run+EXS 重复 finalize → 1 条 |
| release | {release_id} | 同 RELEASE 重复 execute → 1 条 |

- ExperienceBridge.record: 锁内查 (source, source_id) → 存在返回现有 (不重复)
- ExperienceStore.add 同 id 覆盖 (现有) + bridge source_id 幂等 = 双保险
- recovery: TaskRun-2 新 run_id → 新 source_id → 新 exp (确定性, 不串)

## 2. E2E-C5/C6 验证目标

same EXS finalize ×2 → 1 exp; same RELEASE bridge ×2 → 1 release exp。
