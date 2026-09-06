# 10 — FAILURE / RECOVERY CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 冻结 (与 07 一致, 集中)

- 失败 (EXS FAIL / ver FAIL / RELEASE REJECTED) **都产生 exp** (真实失败是
  学习金矿 — 但 P2-C 只记录, P2-D 才消费)
- 恢复 = 新 run 新 exp (旧 FAIL exp 保留 = 历史 attempt 可追踪)
- 禁止: 失败后不记录 / 重试后覆盖旧失败 exp / 把失败记成成功
- RELEASE REJECTED → release 决策 exp (FAILURE_PATTERN, detail=gate missing)
- REVOKED/SUPERSEDED → release 决策 exp (detail 标注)
