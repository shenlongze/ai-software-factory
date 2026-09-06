# 02 — PROVENANCE (P2-C IMPL, 2026-09-06)

- exp anchor FK: task_run_id (run-*) / exs_id (EXS-*) / release_id (RELEASE-*)
- source_id 幂等: execution={run}:{exs} / release={release_id}
- reverse trace (E2E-1 实证):
  exp(execution) → run → task → plan → prd → req → disc → idea (纯 FK)
  exp(release) → RELEASE → EVD/ver/art/EXS/run → task → product
- 无字符串推断 / 无 session / 无 filename provenance
