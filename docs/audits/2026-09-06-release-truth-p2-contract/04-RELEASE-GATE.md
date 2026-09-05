# 04 — RELEASE GATE (P2-A CONTRACT, 2026-09-06)

## 1. Minimum Gate (GATED 条件)

| # | 条件 | 等级 |
|---|---|---|
| 1 | task_run_id / exs_id 存在且非空 | MUST |
| 2 | artifact_ids 非空 (≥1 art-* 存在) | MUST |
| 3 | verification_ids 非空: ≥1 ver-* 存在 | MUST |
| 4 | ver-* status == PASS (release policy) | **MUST** (默认) |
| 5 | evidence_ids 非空: EVD-* 存在且可追溯至 ver | MUST (evidence completeness) |
| 6 | art 全部 state 合法 (GENERATED→APPROVED 路径可达 apply) | MUST |
| 7 | 人工 approval (governance appr-*, release 风险=high) | MUST (policy) |
| 8 | Task/Product provenance 可反查 (task→plan→prd→req→disc→idea) | SHOULD (trace 完整才 RELEASED) |
| 9 | 仓库 git 干净/版本号 | POLICY-DEPENDENT |

## 2. Verification Gate 特别要求 (P2 G-3 解决)

- gate **必须消费 canonical ver-*** (verification_domain store)
- 禁止消费: NodeRun.verification snapshot / test_result / subprocess output /
  report.md / WebUI projection
- release 不实时自跑 pytest (rel-* _run_verification 做法废弃) — 验证属于
  P0 verifier 已产生的 ver-*/EVD-*

## 3. Evidence Gate (P2 G-5 解决)

- EVD-* 是 ver 的可审计证明 (F4 contract 不重定义)
- gate 检查 evidence completeness: 每 ver-* PASS 有 ≥1 支撑 EVD-*
  (evidence_refs/verification_refs 双向可查)

## 4. FAIL 语义

- 任一 MUST FAIL → GATED 不通过 → REJECTED (诚实) / CANDIDATE 重试
- **默认 FAIL→BLOCK**; emergency/override release = 本阶段 OUT OF SCOPE
  (不加 override 路径 — 保持简单)
