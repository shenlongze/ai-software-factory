# S18 Architecture Proposal — Production Release Pipeline & Approval UI

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Release Contract (冻结)
```
release_id / production_run_id / project_id / artifact_ids / verification_ids /
evaluation_ids / approval_ids / state / created_at / started_at / completed_at /
failure_reason / history (append-only) / evidence
```

## 2. State Machine (冻结)
```
PENDING → GATED → APPROVED → RELEASING → RELEASED
                    ↘ BLOCKED (gate 拒绝)
                    ↘ REJECTED (approval rejected)
                    ↘ FAILED (executor/apply 失败)
terminal: RELEASED / BLOCKED / REJECTED / FAILED
```

## 3. Gate 集成 (复用 S17, 不重造)
```
release_service.create → ReleaseRecord
  → check(): GovernanceGate + verification + evaluation + approval (非 stale)
  → execute(): 经 Artifact Lifecycle Apply (真实 workspace) → RELEASED + evidence
```

## 4. Idempotency
- RELEASED run 重复 execute → already_released (no-op)
- 同 run 重复 create → 返回已有 pending/active release

## 5. CLI/API
```
factory release list/status/check/create/execute/history
POST /api/production-runs/{id}/releases
GET  /api/releases(+/{id}/history)
GET  /api/production-runs/{id}/release
POST /api/releases/{id}/execute
```

## 6. Web UI (React, 复用现有栈)
- Production Overview: runs 列表 (state 徽章)
- Production Detail: nodes/verification/evaluation/governance/approval/release
- Approval Center: pending 列表 + approve/reject (调真实 API)
- Release Panel: gate 状态 + blocked reason + execute 按钮

## 7. 安全
- Agent ≠ Human (approve 仅 human, 经 Governance 层拒绝)
- UI 只是 API 投影 (无第二业务逻辑)
- Release 必须经 Lifecycle Apply (非直接写 workspace)
