# 07 — IDEMPOTENCY & RECOVERY (P0-F4 IMPL, 2026-09-05)

---

## 1. Artifact 幂等 (F4 §9)

- create_artifact: exs_id 提供 → 锁内 _find_artifact (node_run_id+exs_id+type)
  已有返回 (原子防 race, 非"查后建")
- E2E-3: 同 EXS 重复 finalize → art 1 条
- execute_node_run (无 exs_id): I10 保持每 attempt 新 art (修复场景不误合并)
- 幂等边界修复 (repo 层, 非 WebUI 补偿)

## 2. Verification 幂等 (F3, 保持)

同 (task_run_id, attempt, verification_type) → 已有 ver-* (F3 未改)

## 3. Evidence 幂等

同 (verification_id, evidence_type, source_ref) → 已有 EVD; attach 幂等不重复 refs

## 4. Recovery (attempt isolation)

- TaskRun-1: art-1 (GENERATED, 不可变 I10) + ver-1 FAIL + EVD-1
- TaskRun-2: art-2 + ver-2 PASS + EVD-2
- 不覆盖旧 attempt: art/ver/EVD 各自唯一 id, node_run_id 隔离 (E2E-4 实证)
- create_artifact exs_id 幂等键含 node_run_id — 不同 run 不串

## 5. 边界

- 收纳失败 → None (run 仍 COMPLETED) — 失败安全但无重试 (Known Limitation)
- EXS 级幂等 (record_invocation) 由 F1 保证 — 每 attempt 新 EXS, 不覆盖
