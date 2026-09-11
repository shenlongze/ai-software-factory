# 01 — CURRENT REALITY (P2 GAP AUDIT, 2026-09-06)

## 1. 已冻结 REAL

- Product Truth: IDEA-*→DISC-*→REQ-*→PRD-*@v→PLAN-*→TASK-* (P1, product_truth store)
- Production Truth: TASK-*→run-*→EXS-*→art-*→ver-*→EVD-* (P0-F4)
- 完整边界: PLAN-*→TASK-*→run-*

## 2. Production 后半环真实状态

| 能力 | 代码 | 真实数据 | 消费链 |
|---|---|---|---|
| art-* | REAL (P0-F4) | E2E 有 | → ver-* (artifact_ids) |
| ver-* | REAL (F3) | E2E 有 | → EVD (evidence_refs) |
| EVD-* | REAL (F4) | E2E 有 | (无后续消费) |
| Release | rel-* 实体 (release_service) | **0 文件** | 只连 M3 production_run |
| Experience | exp-* 84 条 (memory) | REAL 84 | source=execution_records 55 (EXS 桥真) |
| Learning | learning_engine_v2 + learning_engine + learning_loop | **observations/candidates 0; agent_profiles.json 0** | 无真实数据运行 |
| Feedback | refresh→load_agent_profiles→CapabilityRouter (代码通) | **profile 文件 0** | 从未真实闭环 |
