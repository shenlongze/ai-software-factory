# S18 Production Release Pipeline & Approval UI — Completion Report

> 日期: 2026-08-29 | HEAD: (S18 commit) | v1.1.324

## 1. GAP Audit
Governance Gate(S17)已有;缺 Release Contract/State Machine/真实执行/CLI/API/UI。

## 2. Release Contract — REAL
release_id/production_run_id/artifact_ids/verification_ids/evaluation_ids/approval_ids/state/evidence/history(append-only)。

## 3. State Machine — REAL
PENDING→GATED→APPROVED→RELEASING→RELEASED;BLOCKED/REJECTED/FAILED terminal;非法转换拒绝;append-only history。

## 4. Governance 集成 — REAL(复用 S17)
release check = GovernanceGate + verification + evaluation + approval;缺失 → BLOCKED + reason/missing。

## 5. ProductionRun 集成 — REAL
release 绑定 run + immutable artifacts;跨 run approval → stale → BLOCKED。

## 6. Release 执行 — REAL
经 Artifact Lifecycle(逐级 GENERATED→STAGED→REVIEWED→APPROVED→APPLIED)→ 真实 git apply → workspace 真实文件 + evidence。

## 7. Artifact/Evidence — REAL
evidence: {artifact_id, type: apply, result, workspace};真实失败 → FAILED + failure_reason(不 fake)。

## 8. 幂等 — REAL
RELEASED 重复 execute → already_released(no-op)。

## 9. CLI — REAL
factory release list/status/check/create/execute/history(薄代理→Service)。

## 10. API — REAL
POST /api/production-runs/{id}/releases | GET /api/releases(+/{id}/history) | GET /api/production-runs/{id}/release | POST /api/releases/{id}/execute(openapi 157 paths,+6)。

## 11. Web UI — REAL(React)
ProductionPage: runs 列表 + Release Panel(gate 状态/blocked reason/execute)+ Approval Center(approve/reject 调真实 API)。挂 #/workspace/production 路由。前端 tsc 全过。

## 12. Audit — REAL
RELEASE_CREATED/GATED/APPROVED/RELEASING/RELEASED/BLOCKED/FAILED 事件注册 + evidence。

## 13. Real E2E — PASS
approve → RELEASED + workspace x.py 真实存在 + evidence;reject → BLOCKED;missing approval → BLOCKED;corrupt patch → FAILED;重复 execute → no-op。

## 14. 测试 — 11 新增
contract/state machine/blocked(无审批/拒绝)/apply-workspace/幂等/失败不fake/CLI/API/approve-E2E/reject-E2E

## 15. Regression
```
全量 llm + core: 794 passed + 5 skipped (零失败)
前端 tsc: PASS | Zero-Stub: PASS
```

## 16. 修复的真实 bug
- approve_artifact REVIEWED 分支未写 approval_ids(S1 遗留)→ 修
- apply_artifact approval 未传时从 approval_ids 读(I12 满足)
- RELEASE_* 事件未注册 → 补

## 17. Commits
feat(发布): S18 Production Release Pipeline & Approval UI + chore(版本): bump v1.1.324 + tag

## 18. Known Limitations
- Release 目标固定 root/workspace(无独立 deploy target 抽象)
- UI 无自动刷新(手动刷新/操作后刷新)

## 19. Remaining Production Gaps
1. 独立 deploy target(server/container)
2. Release rollback
3. Approval expiration(时间窗)

## 20. Next Recommended Sprint
S19: Multi-Run Production + Release Rollback — 多 run 并行 + release 回滚能力。

## Final Verdict
> **Release Pipeline 真正受到 Governance 约束,Human Approval → Release → Evidence → Audit 完整链路真实成立。**

**S18 = PASS** — 真实 Release(经 Lifecycle Apply 到 workspace + evidence)、Governance Gate 强制(缺审批/拒绝/stale 全 BLOCKED)、幂等(不重复 release)、失败真实记录(不 fake success)、CLI/API/Web UI 三入口共享 Service、全链可审计。
