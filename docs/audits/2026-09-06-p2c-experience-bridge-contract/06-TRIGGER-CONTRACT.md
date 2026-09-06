# 06 — TRIGGER CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 双 trigger (冻结)

### Trigger-1: Production → Experience
- 位置: finalize_node_run 完成 (P0 执行吸收点 — 现有 F4 I8 收纳同位置)
- 时机: EXS 已写 + ver 已物化 + EVD 已挂 → 该 run 的完整执行结果已知
- 语义: 每次**终态 finalize** (COMPLETED 或 FAILED) 后记录
- 失败安全: bridge 异常不阻断 finalize (同 F4 收纳模式)

### Trigger-2: Release → Experience
- 位置: release_truth.execute_release 达 RELEASED / REJECTED / REVOKED
- 语义: release 决策经验 (outcome + gate 结果)

## 2. 非 trigger

- 不每次 EXS 写 (避免中间态)
- 不每次 ver (验证中间结果)
- 不每次 art (产物非结果)
