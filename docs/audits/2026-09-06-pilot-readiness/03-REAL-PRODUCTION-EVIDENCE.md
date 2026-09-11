# 03 — REAL PRODUCTION EVIDENCE (2026-09-06, READ-ONLY)

## 真实库 (~/.factory) — 分类统计

| 域 | 真实生产 | 说明 |
|---|---|---|
| IDEA/DISC/REQ/PRD/PLAN (canonical P1) | 0 | product_truth/* 未在真实库 (E2E tmp only) |
| TASK-*/run-* (canonical P0) | 0 | nodes/ 不存在 |
| EXS-* | 100 | exec/execution_records.json (M3 factory-exec 历史真实) |
| ART-* (legacy) | 225 | exec/artifacts.json (M3) |
| ver-*/EVD-* (canonical) | 0 | verifications.json 不存在 |
| RELEASE-* (canonical P2-A) | 0 | release_truth.json 不存在 |
| exp-* | 84 | M3 AutoLearner (无 anchor, 非 P2-C 新链) |
| OBS/CAND/PROM/PROFILE/RD (P2-D) | 0 | learning/ 未建 |
| **完整成品 (dist zip)** | **2** | workflow_runs/P-69c4f155 + P-17ef31e5 (M3 时代真实) |
| **完整成功 run** | **1** | P-69c4f155: completed, 6/6 stages, 0 errors, deepseek-v4-pro |

## 真实成品内容 (P-69c4f155/R1788174921245/dist/app-1.0.0.zip)
- 台球记分 MVP: app.js (11KB) + index.html (3.9KB) + style.css (4.9KB)
  + tests/smoke_check.py (确定性冒烟: 静态检查+JS 语法+交互断言)
- workflow report: final_workflow_status=completed, 6 stages COMPLETED,
  0 errors, tokens 33K, cost ~$0.012, wall 126s

## 判定
- 系统**曾真实完成** Idea→成品 (证据: zip + report) — 但为 M3 workflow 时代
- canonical 链 (P0-P2D) 真实生产记录 = 0 (E2E 隔离 tmp — 诚实)
- Pilot 需: ① canonical 旅程一次真实成功 ② 接合双链 ③ acceptance 闭环
