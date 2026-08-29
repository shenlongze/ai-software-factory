# S18 Gap Analysis — Production Release Pipeline & Approval UI

> 日期: 2026-08-29 | HEAD: a72132ac (v1.1.323)

## Existing REAL (复用)
| 能力 | 位置 |
|------|------|
| Governance Gate + ApprovalRequest + Release check | governance_service.py (S17) |
| Artifact Lifecycle + Apply (真实 workspace) | artifact_lifecycle.py (S1) |
| Evaluation (S13) / Verification (S5) | production_evaluation / node_runtime |
| Web UI (React 18 + Vite) | factory-console/web/frontend |
| CLI/API pattern (共享 Service) | cli_factory + fastapi_adapter |

## Missing (S18 新增)
| GAP | 最小实现 |
|-----|---------|
| Release Contract + State Machine (PENDING→GATED→APPROVED→RELEASING→RELEASED/BLOCKED/FAILED/REJECTED) | release_service.py |
| Release 真实行为 (Apply → Workspace evidence) | release_service.execute |
| Release 幂等 (RELEASED 不重复执行) | release_service |
| CLI (release list/status/check/create/execute/history) | cli_factory |
| API (POST /api/production-runs/{id}/releases 等) | fastapi_adapter |
| Web UI (Production Overview + Detail + Approval Center + Release Panel) | frontend pages |

## 设计
```
release_service.create(run_id) → ReleaseRecord (PENDING)
  → check() → GATED (GovernanceGate + Evaluation + Verification)
  → execute() → 经 Lifecycle Apply → RELEASED + evidence
状态机 + append-only history + audit
```

## 禁止
- fake release / UI 自己判断 approval / 绕过 Governance / 跨 run 复用 approval
