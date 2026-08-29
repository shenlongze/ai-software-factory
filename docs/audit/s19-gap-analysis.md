# S19 Gap Analysis — Multi-Run Production + Release Rollback

> 日期: 2026-08-29 | HEAD: 2139492b (v1.1.324)

## Existing REAL (复用)
| 能力 | 位置 |
|------|------|
| Multi-Run: run_id 独立 (uuid) + node_runs/artifacts 独立 | production_run.py |
| Release History: 多 release 共存 + evidence + workspace | release_service.py (S18) |
| Governance Gate + Approval (human only) | governance_service.py (S17) |
| Artifact Lifecycle (逐级 + Apply) | artifact_lifecycle.py (S1) |
| Audit events | audit_event.py |

## Missing (S19 新增)
| GAP | 最小实现 |
|-----|---------|
| Rollback Contract + State Machine (PENDING→GATED→APPROVED→ROLLING_BACK→ROLLED_BACK) | rollback_service.py |
| Rollback 真实执行 (经 Artifact Lifecycle apply target release artifacts → workspace) | rollback_service.execute |
| Target Release 验证 (存在/同 project/RELEASED/evidence) | rollback_service.create |
| Rollback Governance (policy + human approval) | rollback_service.check |
| Rollback Evidence + Audit (ROLLBACK_* 事件) | rollback_service |
| Rollback 幂等 (ROLLED_BACK 重复 → no-op) | rollback_service |
| CLI/API/UI | cli_factory + fastapi_adapter + ProductionPage |

## 设计
```
create(project_id, target_release_id) → RollbackRecord (PENDING)
  → check(): governance + verification + approval
  → execute(): 经 Artifact Lifecycle apply target release artifacts → ROLLED_BACK + evidence
历史保留: Release A/B 不变, Rollback R1 是独立事实
```

## 禁止
- git checkout 冒充 / 删除 Release 历史 / global current release / Agent 自批准 / 第二套 workspace 修改
