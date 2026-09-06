# 02 — EVIDENCE (P2-C FINAL ACCEPTANCE, 2026-09-06)

## Writer/SSOT
- experience_bridge.py: record (L51) / record_execution (L97) / record_release (L130)
- 唯一 writer; ExperienceStore 唯一 store; intelligence 仅 docstring 引用

## Trigger (production path)
- agent_loop.py L654 + L1717: finalize_node_run 后 → record_execution
  (两处 production completion path — auto worker + chain dispatch)
- cli_factory.py L6843: release-truth execute → record_release

## Anchor FK
- memory/experience.py: task_run_id/exs_id/release_id/source_id (L79-82)
- from_dict 兼容旧记录 (L139-142) — 84 条 legacy 零伪造 FK

## 测试 (15/15 fresh)
- 幂等: test_idempotent_source_id / test_retry_idempotent / test_release_idempotent
- 失败: test_ver_fail_not_fake_success / test_rejected_failure
- 恢复: test_recovery_new_run_new_exp
- 隔离: test_legacy_no_fk_records_load / test_intelligence_not_read
- 全链: test_release_to_experience_full_chain / test_reverse_trace
