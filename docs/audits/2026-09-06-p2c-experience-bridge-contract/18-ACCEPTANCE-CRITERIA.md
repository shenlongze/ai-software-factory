# 18 — ACCEPTANCE CRITERIA (P2-C CONTRACT, 2026-09-06)

C1 exp ID frozen (exp-*) | C2 SSOT frozen (memory/experience_store.json) |
C3 single writer (ExperienceBridge) | C4 production provenance (run+exs anchor) |
C5 release provenance (release_id) | C6 lifecycle (immutable, 无复杂状态机) |
C7 trigger (finalize 后 + release 后) | C8 failure semantics (失败也记录) |
C9 recovery (新 run 新 exp) | C10 release rejection (REJECTED→exp) |
C11 idempotency ((source, source_id)) | C12 legacy isolation (84 条不迁移) |
C13 P0 zero-diff | C14 P1 zero-diff | C15 P2-A zero-diff |
C16 WebUI projection | C17 CLI/API 不 bypass writer | C18 Production→exp E2E |
C19 Release→exp E2E | C20 reverse trace exp→production→product |
C21 无重复 (retry 幂等) | C22 无 migration/backfill | C23 无 Learning 实现 |
C24 无 false closure
