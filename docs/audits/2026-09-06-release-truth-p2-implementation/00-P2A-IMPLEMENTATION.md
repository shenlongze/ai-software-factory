# 00 — P2-A RELEASE TRUTH IMPLEMENTATION (2026-09-06)

> Sprint: P2-A Release Truth — Release 接入 P0 Canonical | Status: PASS
> 基线: 04299e26 | 依据: P2-A Contract Freeze (GO)

## 1. 实现

- factory-console/release_truth.py (新): RELEASE-{hex8} canonical Release
  - store: <root>/releases/release_truth.json (独立 — rel-* M3 同文件会 id 混列
    + M3 create KeyError, 故隔离)
  - lifecycle: CANDIDATE→GATED→RELEASED→SUPERSEDED/REVOKED/REJECTED (受控转换)
  - create 自动收集 P0 canonical FK: art-* (artifact_ids), ver-* (verification_ids),
    EVD-* (evidence_ids), run/EXS/task
  - gate: 消费 ver-* (PASS) + EVD-* (completeness) + art + provenance — 不自跑验证
  - execute: governance approval (subject_type=release) 后 RELEASED (FAIL→BLOCK)
  - trace_release: reverse FK 全链 (RELEASE→…→IDEA, 复用 P1 reverse_trace)
  - idempotency: 同 (task_run, exs) 非 terminal / idempotency_key → 单 release
- governance_service.py: subject_type 白名单 + "release" (最小增量; M3 release
  策略 policy_id=release 已存在)
- cli_factory.py: release-truth create/gate/trace/list 命令
- tests/console/test_p2_release_truth.py (新, 14)

## 2. 契约达成

- Release consume P0 facts, 零 reverse-write / 零自跑 pytest / 零产 Artifact
- rel-* (M3) 完全隔离 (独立文件, 零迁移)
- negative paths 实证: ver FAIL → REJECTED; missing EVD → REJECTED (均 ≠RELEASED)
