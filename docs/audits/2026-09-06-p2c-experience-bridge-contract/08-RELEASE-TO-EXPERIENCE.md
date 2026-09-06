# 08 — RELEASE → EXPERIENCE (P2-C CONTRACT, 2026-09-06)

## 1. 方案选择: A+B 组合语义 (不复制)

### Release Outcome Experience (新 — 只在 RELEASE 终态)
- RELEASED → source="release", type 沿用 SUCCESS_PATTERN (outcome),
  release_id anchor, source_id=f"release:{release_id}"
- REJECTED → source="release", type=FAILURE_PATTERN (decision 经验),
  release_id anchor (含 gate missing 理由入 detail) — **REJECTED 产生经验** (任务书 §17)
- REVOKED/SUPERSEDED → source="release", type 标注 (detail)

### Execution Experience (已有 — 附加 release_id)
同一 (run, exs) 的执行经验**不复制** — Release 达 RELEASED 时:
  - 若执行经验存在 → 更新附加 release_id? → **禁止 UPDATE** (immutable)
  - 决定: 执行经验保持纯 execution; release 决策是独立经验 (release_id anchor)
  → 无重复学习 (执行经验 1 条 + release 决策经验 1 条, 语义不同)

## 2. 明确

Execution Experience 与 Release Outcome Experience = **两个不同事实**
(执行结果 vs 发布决策) — 不合并不复制。
