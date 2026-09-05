# 01 — RELEASE ENTITY (P2-A IMPL, 2026-09-06)

```
release_id        RELEASE-{hex8}
status            CANDIDATE→GATED→RELEASED→SUPERSEDED/REVOKED/REJECTED
task_id           TASK-* (经 run 自动)
task_run_id       run-*
exs_id            EXS-*
artifact_ids      [art-*]    (create 自动收集)
verification_ids  [ver-*]    (create 自动收集 — gate 消费)
evidence_ids      [EVD-*]    (create 自动收集 — gate 消费)
reason / actor / idempotency_key / gate (快照) / history
metadata          (git ref 等 external — 非 SSOT)
```

store: releases/release_truth.json | writer: release_truth 模块函数 (唯一)
