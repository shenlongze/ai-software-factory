# S21 Architecture Proposal — Production Health Monitor & Automatic Rollback

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Health Contract (冻结)
```
HealthCheck: check_id / release_id / run_id / check_type / status(PENDING/RUNNING/PASSED/FAILED)
             / result(HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN) / started_at / completed_at
             / evidence / history
```

## 2. Health Policy (冻结)
```
all checks PASS → HEALTHY
transient fail (retryable) → DEGRADED
persistent fail → UNHEALTHY → rollback candidate
bounded, deterministic, auditable (无 LLM 判断)
```

## 3. Health Incident (冻结)
```
incident_id / release_id / run_id / severity / health_result / failed_checks /
recommended_action / status(OPEN/ACKNOWLEDGED/RECOVERING/RESOLVED/FAILED) /
evidence / history(append-only) / timestamps
同 release 同故障去重 (active incident 存在则不重复创建)
```

## 4. Recovery Flow (冻结)
```
HealthMonitor(观察) → Incident(OPEN) → recover(incident)
  → rollback_service.create/execute (复用 Governance + Lifecycle + Verification)
  → rollback verification PASS → RESOLVED; FAIL → incident FAILED
```

## 5. 边界
- HealthMonitor 不写 workspace / 不绕过 rollback_service / 不调用 LLM
- 复用 integrity_lock (并发安全) + rollback idempotency

## 6. CLI/API
```
factory production health <run_id> | health-check <release_id> | incidents | incident <id> | recover <id>
GET /api/production-runs/{id}/health | POST /api/releases/{id}/health-check
GET /api/health-incidents(+/{id}) | POST /api/health-incidents/{id}/recover
```
