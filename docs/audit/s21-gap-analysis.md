# S21 Gap Analysis — Production Health Monitor & Automatic Rollback

> 日期: 2026-08-29 | HEAD: aa88926b (v1.1.327)

## EXISTING (复用)
| 能力 | 位置 |
|------|------|
| Rollback Service (create/check/execute + state machine + idempotency) | rollback_service.py |
| Verification (verify_pytest/verify_python_syntax 真实 subprocess) | verification.py |
| Release Service (state machine + VERIFYING recovery) | release_service.py |
| Governance (human approval) | governance_service.py |
| 跨进程锁 | integrity_lock.py |
| Recovery VERIFYING | release/rollback recover_verifying |

## MISSING (S21 新增)
| GAP | 最小实现 |
|-----|---------|
| HealthMonitor (观察不执行) | health_service.py |
| HealthCheck Contract (check_id/status/evidence) | health_service.py |
| HealthPolicy (HEALTHY/DEGRADED/UNHEALTHY 确定性) | health_service.py |
| HealthIncident (OPEN/RECOVERING/RESOLVED/FAILED + append-only) | health_service.py |
| Automatic Recovery (Incident → policy → rollback_service) | health_service.py |
| HEALTH_* audit events | audit_event.py |
| CLI/API | cli_factory + fastapi_adapter |
| UI (ProductionPage 加 Health/Incidents) | ProductionPage.tsx |

## 设计
```
Release → health_check(release_id) → HealthResult
  → policy 判定 HEALTHY/DEGRADED/UNHEALTHY
  → UNHEALTHY → Incident(OPEN) → recover(incident)
     → rollback_service.create/execute (复用) → rollback verification
     → RESOLVED / FAILED
HealthMonitor 只观察;Rollback 经现有 Service (Governance + Lifecycle)
```

## 禁止
- HealthMonitor 直接写 workspace / 绕过 rollback_service / LLM 决定 rollback / 无限 loop
