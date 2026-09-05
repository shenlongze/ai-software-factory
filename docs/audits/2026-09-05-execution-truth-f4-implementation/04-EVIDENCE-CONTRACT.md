# 04 — EVIDENCE CONTRACT (P0-F4 IMPL, 2026-09-05)

> F4 后 canonical Evidence (EVD-*) 落地状态

---

## 1. Domain (evidence_domain.py)

- identity: EVD-{uuid4.hex[:10]} (与 ev-* M3 分离)
- store: `<root>/evidence/EVD-*.json` (每 EVD 一文件)
- writer: materialize_evidence 唯一 (RLock + tmp+os.replace)
- 读: get_evidence / list_evidence(verification_id 过滤) / count

## 2. Schema

```
evidence_id         EVD-*
verification_refs   [ver-*]   (创建者引用; 共享=attach 追加)
evidence_type       verifier_output / pytest_output / ... (真实生产材料)
source_ref          pytest -q / verifier 标识
content             真实 verifier 输出 (≤20000)
metadata            {verifier_meta: {score/tests/exit_code/source}}
actor / created_at
immutable           True
```

## 3. 语义 (D2) — 达成

- EVD-* = 支撑 Verification 结论的真实事实材料 (为什么值得相信)
- 禁止 fake: _attach_verify_evidence 仅当 verify_meta 含真实内容 (method +
  stdout/stderr/error/reason) 物化; 无内容 → 不伪造 (F4 §15, 测试实证)
- EVD ≠ Verification (ver 才是 PASS/FAIL/UNKNOWN) ≠ Artifact ≠ Approval ≠ Audit

## 4. 关系 (D3)

- Verification → Evidence[]: EVD.verification_refs 含 ver-* (E2E-1: ver→EVD)
- Evidence 共享: attach_evidence 追加 refs (多 Verification 引用同一 EVD;
  不可变 content) — 测试实证
- 不建 EXS→EVD 直接 FK (经 ver/art 可达)

## 5. Idempotency

同 (verification_id, evidence_type, source_ref) → 返回已有 (测试实证)。
E2E-3: 重复 finalize EVD 保持 1。
