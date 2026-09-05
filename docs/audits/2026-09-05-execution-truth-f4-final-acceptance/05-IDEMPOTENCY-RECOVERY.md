# 05 — IDEMPOTENCY & RECOVERY (P0-F4 ACCEPTANCE, 2026-09-05)

---

## 1. Idempotency (F4 §15)

### Artifact
- create_artifact: exs_id 提供 → **锁内** _find_artifact (node_run_id+exs_id+type)
  已有 → 返回已有 (非 query-then-create race; RLock 保护整个查+写)
- E2E-3: 同 EXS 重复 finalize → art 1→1
- execute_node_run (无 exs_id): I10 每 attempt 新 art (修复语义, 非误合并)

### Verification (F3 保持)
- 同 (task_run_id, attempt, verification_type) → 已有 ver-* (F3 幂等键未改)

### Evidence
- 同 (verification_id, evidence_type, source_ref) → 已有 EVD; attach 幂等不重复

### E2E-3 汇总
art 1→1 | ver 1→1 | EVD 1 (重复 completion callback 无重复 canonical facts)

## 2. Recovery (F4 §16) — attempt isolation

```
TaskRun-1: EXS-1 → art-1 → ver-1 (FAIL) → EVD-1
TaskRun-2: EXS-2 → art-2 → ver-2 (PASS) → EVD-2   (recovery 新 run)
```

- 不覆盖: art/ver/EVD 各唯一 id; art.node_run_id 隔离 (create exs 幂等键含
  node_run_id — 不同 run 不串)
- E2E-4 fresh 复跑实证: run2/art2/ver2 FAIL vs run3/art3/ver3 PASS, 全独立

## 3. 结论

**Idempotency PASS | Recovery PASS** (代码锁内幂等 + E2E-3/4 实证)
