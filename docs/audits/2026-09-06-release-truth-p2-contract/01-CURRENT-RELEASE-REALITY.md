# 01 — CURRENT RELEASE REALITY (P2-A CONTRACT, 2026-09-06)

## 1. Inventory (代码取证)

| 对象 | 位置 | 状态 |
|---|---|---|
| rel-* entity | release_service.py (rel-{hex10}) | **LEGACY (M3 域)** |
| store | <root>/releases/releases.json | 真实 0 条 |
| lifecycle | PENDING→GATED→APPROVED→RELEASING→VERIFYING→RELEASED/BLOCKED/REJECTED/FAILED (9 态) | 完整 (M3) |
| gate | check(): M3 run.state==COMPLETED + governance + M3 evaluation | M3 |
| execute | gate→apply_artifact (S2 lifecycle)→governance approval→_run_verification→RELEASED | 机制可复用 |
| _run_verification | 对 workspace 实时 pytest/syntax (checks 存 rel.evidence) | 自验证 (非 P0 ver-*) |
| verification_ids | 恒空 [] (从不引用 P0 ver-*) | 断链 |
| CLI | factory release list/status/check/create/execute/history/verify | M3 target |
| API | /api/production-runs/{id}/releases + /api/releases* | M3 |
| governance | appr-* (governance/approvals.json 8 条真实) | 独立可用 |
| WebUI | ops control-tower 投影 | 展示 |
| 真实 release | **0 条** (从无 M3 production_run 真实运行) | MOCK/EMPTY |

## 2. 关键判断

- rel-* 执行机制 (apply+governance+verify) 设计良好, 可作新 Release 的
  action 参考 — 但上游 (M3 production_run) 与验证源 (自跑 pytest, 非 ver-*)
  都与 P0 canonical 断链
- verification_ids 字段恒空 = rel 从不消费 P0 ver-* (P2 G-3 证据)
- Release→Task 无 trace (rel 只连 M3 run, M3 run 不连 P0 TASK-*) (P2 G-4)
