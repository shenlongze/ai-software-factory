# 03 — RELEASE AUDIT (P2 GAP AUDIT, 2026-09-06)

## R1 Release Entity
存在: rel-{hex10} (release_service.py), store = <root>/releases/releases.json
**真实文件 0**。lifecycle PENDING→…→RELEASED。writer = release_service.create。

## R2 Release Input
create(production_run_id) — production_run = **M3 (production_run.py)**。
artifact_ids 复制自 M3 run.artifacts。**不消费 P0 run-*/EXS/art-*/ver-*/EVD-***。

## R3 Release Gate
check(): run.state==COMPLETED (M3) + governance + evaluation (M3 production_evaluation)
**无 P0 ver-* PASS 检查**。测试 test_release.py 全走 M3 create_production_run —
mock 场景 PASS, 真实 P0 链无法到达 release。

## R4 Release Output
execute → apply_artifact (真实 workspace) + RELEASED + evidence — 代码完整
(artifact apply 真实) 但基于 M3 artifact (S2 art-* 共用, 但 run 溯源 M3)。

## R5 Release Persistence
releases/releases.json — 真实 0 条 (从无 production_run 真实运行 → 无 release)。

## R6 Release→Task Traceability
release→M3 production_run→(M3 task-e1-*) — **不连 P0 TASK-*/PLAN-*/PRD-***。
断点: release 无法反查 P0/P1 Product Truth。

## 结论
RELEASE = M1 (实体/CLI/API 全在但挂 M3 空壳; 与 P0/P1 canonical 断链; 真实 0)。
**RELEASE 无 canonical SSOT (rel-* 是 M3 域孤儿 — 非 P0/P1 链一部分)**。
