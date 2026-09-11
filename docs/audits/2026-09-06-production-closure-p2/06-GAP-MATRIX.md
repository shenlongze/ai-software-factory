# 06 — GAP MATRIX (P2 GAP AUDIT, 2026-09-06)

| # | GAP | 分类 | 证据 |
|---|---|---|---|
| G-1 | Release 只连 M3 production_run, 不连 P0/P1 canonical | **P2** | release_service create(production_run_id); production_run.py; test 全 M3 |
| G-2 | Release 真实数据 0 (无 canonical release fact) | P2 | releases/releases.json 空 |
| G-3 | Release gate 无 P0 ver-* 检查 | P2 | check() 读 M3 run.state/evaluation |
| G-4 | Release→Task 无 traceability (不连 TASK-*/PLAN-*/PRD-*) | P2 | rel 只连 M3 run |
| G-5 | EVD-* 无消费端 (evaluation/release 不读) | P2 | production_evaluation 读 M3 内嵌 |
| G-6 | learning_engine_v2 observations/candidates 0 数据 | P2 | intelligence/ 无文件 |
| G-7 | agent_profiles.json 0 (refresh 从未真实运行) | **P2 (Learning 闭环核心)** | ~/.factory/memory/agent_profiles.json 不存在 |
| G-8 | refresh 仅手动 (actions_memory), 无自动生产后触发 | P2 | grep 调用点 |
| G-9 | release/evaluation 域与 P0 双执行系统并存未治理 | P2 | M3 production_run vs P0 run-* |
| G-10 | M3 orchestrator 触发 AutoLearner 而非 P0 链 | P2 | orchestrator.py:2187 |
| G-11 | Release CLI/API 展示 (list/status) 无真实 fact | P3 | API 有, 数据 0 |
| G-12 | ops/control-tower 投影 | P3 | 展示层 |

**无 P0/P1 GAP (不破坏已冻结 contract)** — 全为 P2/P3。
