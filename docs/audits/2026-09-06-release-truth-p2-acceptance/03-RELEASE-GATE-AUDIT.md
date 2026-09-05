# 03 — RELEASE GATE AUDIT (P2-A ACCEPTANCE, 2026-09-06)

## 1. Gate = canonical evidence consumer (非第二验证系统)

强制检查 (grep): release_truth.py 零 pytest / 零 _run_verification /
零 verify_python_syntax / 零 subprocess / 零 NodeRun.verification /
零 production_run — **PASS**

Gate 消费:
- ver-*: verification_domain.get_verification (status==PASS 才过)
- EVD-*: evidence_domain.list_evidence (每 PASS ver 有 ≥1 EVD)
- art-*: artifact_lifecycle.list_artifacts (≥1)
- provenance: task_run_id/exs_id 非空

## 2. Artifact / Verification / Evidence / Approval / Provenance 全 MUST

gate_release missing 分类: artifact / verification / verification_not_pass /
evidence_missing / task_run / exs — 全真实 domain 读。

## 3. execute 双门

gate 重评 (最新 ver/EVD) + governance approval (subject_type=release,
decision==APPROVED) — 无 approval → ValueError BLOCK。
