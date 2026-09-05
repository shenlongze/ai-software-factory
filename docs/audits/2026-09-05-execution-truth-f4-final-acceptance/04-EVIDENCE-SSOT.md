# 04 — EVIDENCE SSOT (P0-F4 ACCEPTANCE, 2026-09-05)

> D2/EVD 验收

---

## 1. EVD-* 唯一 canonical Evidence

- identity: EVD-{hex10} (evidence_domain)
- writer: materialize_evidence 唯一 (调用点仅 node_runtime:384 _attach_verify_evidence)
- store: <root>/evidence/EVD-*.json
- 语义: 支撑 Verification 结论的真实事实材料 (真实 verifier 输出)

## 2. ev-* 仍 legacy (M3 approval package)

- ev-* EvidenceBundle 写入方 (repo_mode/orchestrator/backlog_sweeper) 未改 —
  仍 M3 审批包
- 无 ev-* → EVD-* 转换 (grep 零命中); 无 ev-* 被 EVD 域读取
- 路径隔离: ev-* 在 projects/{slug}/evidence/; EVD-* 在 <root>/evidence/
  (测试 test_legacy_evd_prefix_disjoint 实证)

## 3. Evidence 真实 (非 metadata)

- EVD 内容 = 真实 verifier 输出 (E2E-1: pytest stdout 物化)
- 无内容 → 不伪造 (test_no_content_no_fake_evidence: tests=1 无输出 → 0 EVD)
- 禁止 "verification passed" 式空 EVD (F4 §15 达成)

## 4. Shared Evidence (M:N)

- EVD.verification_refs = [ver-*] 数组; attach_evidence 追加引用
- 1 EVD → 多 Verification 引用 (schema 不强制 1:1; 测试实证)

## 5. 结论

**EVD SSOT PASS | ev-* legacy PASS | Evidence 真实 PASS | Shared PASS**
