# 07 — TRUTH CHAIN (P0-F4 ACCEPTANCE, 2026-09-05)

> 逐级 Production Truth Chain 验收

---

## 1. 逐级属性

| 级 | identity | canonical owner | writer | repository | relation | 幂等 | 恢复 |
|---|---|---|---|---|---|---|---|
| Task | TASK-* | ManagementStore | service.create_task | backlog task.json | → run | F1 | — |
| TaskRun | run-* | node_runtime | create_node_run | nodes/runs/*.json | task_id=TASK | F1 | 新 run |
| EXS | EXS-* | record_invocation | gateway | exec/execution_records.json | task_run_id=run | F1/F2 | 新 EXS |
| Artifact | art-* | S2 lifecycle | create_artifact | artifacts/xx/art-*.json | node_run_id+exs_id | exs 锁内幂等 | 新 art (I10) |
| Verification | ver-* | verification_domain | materialize_verification | verifications.json | task_run_id/exs_id/artifact_ids | 幂等键 | 新 ver |
| Evidence | EVD-* | evidence_domain | materialize_evidence | evidence/EVD-*.json | verification_refs | 同源幂等 | 新 EVD |

## 2. Fresh E2E-1 实证 (2026-09-05 复跑)

```
TASK-f4e1 → run-* (task_id 锚)
  → EXS (result_id, task_run_id 锚)
  → art-* (GENERATED, exs_id=EXS, node_run_id=run)   [I8 收纳]
  → ver-* PASS (artifact_ids=[art-*])
  → EVD-* (verifier_output, content=真实 pytest 输出, verification_refs=[ver])
全 ID 反查: art→run→task; ver→art→exs; EVD→ver  — 每级真实持久化
```

## 3. audit visibility

- 每级产生 audit observation: TASK_CREATED (service), NODE_RUN_* (node_runtime),
  artifact transitions (artifact_lifecycle _record_transition), VERIFICATION_*
  (verification_domain emit_audit), EVD 创建 (待 future emit)
- audit 是观察层, 非 SSOT (不用于重建 domain facts)

## 4. CLI/API projection

- CLI: factory artifact list|get (art-*) / evd list|get (EVD-*) /
  verification list|get (ver-*) — 全部读 canonical domain (实测 rc=0)
- API: T-9 trace 投影 verifications (F3); /api/artifacts 为 org S9 投影 (非 canonical)

## 5. 结论

**Truth Chain PASS** — TASK → run → EXS → art → ver → EVD 每级真实持久化 +
唯一 owner + 幂等 + 可恢复 + 可审计, 无第二事实。
