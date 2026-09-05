# 09 — TEST EVIDENCE (P0-F4 IMPL, 2026-09-05)

> 测试证据 — 全量回归 + F4 新增

---

## 1. F4 新增测试 (14, tests/console/test_p0_f4_artifact_evidence.py)

| Test | 验证 |
|---|---|
| test_success_absorbs_artifact | I8: finalize 收纳 art-* (type=report, exs_id, run) |
| test_artifact_idempotent_per_exs | 同 EXS 重复 → 单 art |
| test_no_exs_no_artifact | 无 EXS 不收纳 (不伪造) |
| test_failure_no_artifact | 执行失败不产 art |
| test_i8_verification_linked_artifact | ver.artifact_ids → art |
| test_execute_produces_artifact_and_ver | workflow: art + ver 关联 |
| test_execute_attaches_real_evidence | 真实 verifier 输出 → EVD |
| test_evd_identity_and_relation | EVD identity + verification_refs |
| test_evd_idempotent | 同源重复 → 单 EVD |
| test_evd_shared_across_verifications | EVD 多 Verification 共享 |
| test_evd_requires_verification_and_type | 必填校验 |
| test_no_content_no_fake_evidence | 无内容不伪造 EVD (F4 §15) |
| test_legacy_evd_prefix_disjoint | ev-*/EVD-* 隔离 |
| test_verify_evidence_ref_kept_f3 | F3 evidence_ref 保留 |

## 2. 回归结果

- F1 16/16 + F2 8/8 + F3 17/17 + F4 14/14 = 55/55
- 核心套件 (org/exec/console/llm/benchmark 相关): **2684 passed, 0 failed**
- llm 全量: 829 passed, 6 skipped, 0 failed
- 既有 artifact/node/repair/recovery/evaluation/experience 全过 (无 F4 归因失败)

## 3. 预存/偶发 (非 F4 归因)

- test_agent_loop 11 failed = 预存 (历轮对照一致)
- test_concurrency 偶发 (多进程时序, 单独跑通过)

## 4. 真实 E2E

4/4 PASS (06-E2E-EVIDENCE.md): SUCCESS / VERIFY FAIL / IDEMPOTENCY / RECOVERY
