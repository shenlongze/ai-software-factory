# S19 Architecture Proposal — Multi-Run Production + Release Rollback

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Multi-Run Contract (已有, 冻结)
```
Project → ProductionRun A (uuid) → Release A
Project → ProductionRun B (uuid) → Release B
完全独立: run_id/node_runs/artifacts/verification/evaluation/approval/release
```

## 2. Rollback Contract (冻结)
```
rollback_id / project_id / target_release_id / from_release_id /
artifact_ids / verification_ids / approval_ids / state / reason /
evidence / history (append-only) / created_at / completed_at / failure_reason
```

## 3. Rollback State Machine (冻结)
```
PENDING → GATED → APPROVED → ROLLING_BACK → ROLLED_BACK
                ↘ BLOCKED / REJECTED / FAILED (terminal)
```

## 4. Target Rules (冻结)
- target Release 必须存在 + 同 project + RELEASED + 有 evidence
- 跨 project → BLOCKED;伪造 release_id → ERROR

## 5. 执行 (冻结)
```
target Release artifacts → 逐级 Artifact Lifecycle → Apply patch → workspace
→ ROLLED_BACK + evidence (非 git checkout, 非重新执行 ProductionRun)
```

## 6. Governance (冻结)
- rollback policy = high + human approval (复用 S17)
- approval 绑定 target release/artifacts; 跨 run → STALE/BLOCKED

## 7. Immutability / Idempotency
- Release A/B 历史不变 (Rollback R1 是独立事实)
- ROLLED_BACK 重复 execute → no-op

## 8. CLI/API/UI
```
factory rollback list/status/check/create/execute/history
POST /api/releases/{id}/rollbacks | GET /api/rollbacks(+/{id}/history/check) | POST /api/rollbacks/{id}/execute
UI: Release Panel 加 Rollback 按钮 + 状态 (真实 API)
```
