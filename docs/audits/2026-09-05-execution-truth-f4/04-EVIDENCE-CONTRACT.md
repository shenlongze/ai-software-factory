# 04 — EVIDENCE CONTRACT (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> Evidence 现状 — M3 EvidenceBundle (不是 F4 目标语义的 Evidence domain)

---

## 1. EvidenceBundle (session/evidence.py)

- identity: `ev-{hex8}` (bundle_id)
- 结构: {bundle_id, project_id, task_id, agent_id, diff, test_results[], logs[],
  decisions[], artifacts[], evaluation?, created_at, status: pending/approved/rejected/applied}
- 持久化: EvidenceStore → projects/{slug}/evidence/ev-*.json
- 写者: EvidenceBuilder (repo_mode.from_repo_result) / orchestrator._m3_evidence / cli
- 读者: cli evidence list/show / backlog_sweeper / task_tree
- 审计: emit_evidence_created → EVIDENCE_BUNDLE_CREATED

## 2. 语义判定

EvidenceBundle = **M3 时代"变更审批证据包"** (diff+测试+决策+产物, status=
pending/approved/applied) — 是 M3 产物审批的证据载体。

≠ F4 目标语义: "支撑 Artifact/Verification/Task completion 的不可变事实依据"。

- artifacts[] 字段真实数据全空 (9/9)
- test_results 全空 (M3 域, 非当前 canonical 测试证据)
- task_id = ai-factory 旧 slug (M3), 非 TASK-*

## 3. 真实数据

9 条 ev-* (projects/ai-factory-self/evidence/), 全 M3 痕迹, 零 canonical 关联。

## 4. 结论

Evidence domain 存在**单套** (ev-* EvidenceBundle) 但语义是 M3 审批包 —
F4 若需"支撑 Ver/Artifact 的证据", 要么复用/泛化 EvidenceBundle (需定义新关系),
要么新建 (需决策)。无第二套 Evidence 账本 (非多 SSOT — 但语义不匹配)。
