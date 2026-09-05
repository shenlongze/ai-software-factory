# 10 — ACCEPTANCE (P2-A CONTRACT FREEZE, 2026-09-06)

## 1. C1-C18 核对

C1 Canonical Release entity: ✓ RELEASE-* (02)
C2 Canonical ID: ✓ RELEASE-{hex8}
C3 SSOT: ✓ releases.json (RELEASE-* 段)
C4 Unique writer: ✓ ReleaseService (03/07)
C5 Lifecycle: ✓ 7 态 (03)
C6 Artifact→Release FK: ✓ artifact_ids[] (02)
C7 Verification→Release FK: ✓ verification_ids[] (02)
C8 Evidence→Release FK: ✓ evidence_ids[] (02, 经 ver)
C9 TaskRun→Release provenance: ✓ task_run_id/exs_id (02)
C10 Gate 消费 ver-*: ✓ MUST (04)
C11 Gate 消费 EVD-*: ✓ MUST (04)
C12 Release→TASK reverse trace: ✓ (05)
C13 Release→Product Truth trace: ✓ (05)
C14 Legacy rel-* 隔离: ✓ (06)
C15 No migration/backfill: ✓ (06)
C16 Git tag ≠ Release Truth: ✓ (02 metadata)
C17 WebUI = projection: ✓ (07)
C18 Learning boundary: ✓ (08)

## 2. 无 STOP condition 触发

P0/P1 contract 足够 (release 只 consume, FK 全存在); 无多 Release SSOT
(rel-* 已标 legacy, RELEASE-* 唯一); 不需伪造历史; 不需迁移。

**Status: GO (contract 级)**
