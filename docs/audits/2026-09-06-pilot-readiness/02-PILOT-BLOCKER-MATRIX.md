# 02 — PILOT BLOCKER MATRIX (2026-09-06, READ-ONLY)

| ID | Severity | Stage | User Impact | Exact Failure | Code Path | Evidence | Fix 方向 |
|---|---|---|---|---|---|---|---|
| PB-1 | P0 | 全链 | 用户产出的成品无 canonical 账本证明 (ver/art/EVD/RELEASE) | 用户旅程走 workflow_runner (M3 workflow), canonical P0-P2D 链零接入 | workflow_runner.py (零 finalize_node_run/experience_bridge/release_truth 引用); fastapi project chat → start_project_workflow | grep 证实双链并行 | 把 workflow_runner finalize 接到 P0 吸收 (task/run/EXS/ver/EVD/RELEASE) |
| PB-2 | P0 | Acceptance | 用户无法 review/preview 并提出修改后回到生产 | 无 acceptance/preview 阶段; chat 只 update idea 重跑整链 | chat_route (idea 更新+start); 无 diff-review/preview API | workflow_runner 无 acceptance 步 | 加 preview/diff + acceptance gate + 修改回到 repair/新 run |
| PB-3 | P1 | 全链 | 新用户端到端未复现 (历史成功=1, M3 时代, 非 canonical) | 无 recent canonical 旅程成功记录; canonical 域真实数据 0 | ~/.factory canonical stores 全 0; 成功 zip 在 M3 workflow_runs | report.json (P-69c4f155 completed) | 用 canonical 链跑一次真实端到端 pilot |
| PB-4 | P1 | WebUI | workflow 详情/实例 = mock fallback (诚实标注但非真后端) | runtime 8 阶段链无真后端 | frontend api/runtimeClient.ts (is_mock=true fallback) | 代码注释: 无后端→mock fallback | 后端补 runtime/workflow 状态 API 消除 mock |
| PB-5 | P2 | Verify | 冒烟测试非 canonical ver-* | DevTestLoop 用 smoke_check 非 canonical 验证 | workflow_runner → exec.tester loop | 无 verifications.json 写入 | 接 P0 ver-*/EVD-* 吸收 |
| PB-6 | P2 | Delivery | 成品为 zip 无 git 版本/deploy | ReleaseAgent M3, 无 RELEASE-*/git tag | exec/release.py ReleaseAgent | 无 release_truth 引用 | 接 P2-A RELEASE-* + git tag |
