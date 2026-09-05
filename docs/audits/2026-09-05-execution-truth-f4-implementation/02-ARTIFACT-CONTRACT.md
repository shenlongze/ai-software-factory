# 02 — ARTIFACT CONTRACT (P0-F4 IMPL, 2026-09-05)

> F4 后 canonical Artifact (S2 art-*) 落地状态

---

## 1. Identity / Store / Writer

- identity: art-{uuid4.hex[:12]} (S2, 未改)
- store: `<root>/artifacts/{前缀2}/art-*.json` (前缀分片, I10 不可变)
- writer: artifact_lifecycle.create_artifact 唯一 (锁内查+写)

## 2. Lifecycle

S2 8 态 (GENERATED→STAGED→REVIEWED→APPROVED→APPLIED→VALIDATED→COMMITTED→
RELEASED) + FAILURE_STATES + APPROVAL_GATES + EVIDENCE_REQUIRED_TRANSITIONS —
**未重定义, 原样复用** (D1)。

## 3. F4 扩展 (向后兼容)

- 新字段: `exs_id` (create_artifact 可选参数, 默认空 — 旧调用不传不变)
- 幂等: exs_id 提供时 → 同 (node_run_id, exs_id, type) 已存在返回已有
  (锁内原子查+写, 防 race); node_run_id-only (workflow execute) → I10 每 attempt 新

## 4. 关系 (D3)

- art.node_run_id → run-* (S2 已有)
- art.exs_id → EXS-* (F4 新增, E2E-1 实证)
- ver.artifact_ids → art-* (D3 ver↔art; F4 在物化 ver 时注入)

## 5. I8 (D4) — 达成

finalize_node_run 成功分支 → _absorb_execution_artifact → art-* (GENERATED),
属 production execution contract (同函数内吸收), 非事后补登记。
E2E-1: EXS-ccf5e6c5 → art-baf9daf15564 (同 finalize 内)。

## 6. 多 Artifact ↔ 1 TaskRun/EXS

- TaskRun → Artifact[]: execute_node_run 每 attempt 新 art (I10), E2E-4 实证
  run2/art2 vs run3/art3
- EXS → Artifact[]: create_artifact exs_id 幂等允许同 EXS 多 type (每 type 一 art)
  — 当前 chain 收纳 type=report 单一; 未来扩展 type 即多 art (contract 支持)
