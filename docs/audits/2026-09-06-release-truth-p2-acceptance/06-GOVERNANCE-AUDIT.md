# 06 — GOVERNANCE AUDIT (P2-A ACCEPTANCE, 2026-09-06)

- governance_service 改动 = subject_type 白名单 + "release" (单行, 纯增量向后兼容)
- policy_id=release (risk=high, approval_required=True — 既有 POLICIES)
- execute 无 approval → BLOCK (FAIL→BLOCK 语义, E2E-4)
- 回归: tests/llm/test_governance.py + console governance 相关 77 passed —
  白名单加 release 零破坏既有 subject types
