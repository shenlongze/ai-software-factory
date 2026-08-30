# S22 Architecture Proposal — Continuous Production Operations & Control Tower

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Schedule Contract (冻结)
```
schedule_id / project_id / release_id / check_type / interval_seconds /
enabled / next_run_at / last_run_at / last_result / created_at / updated_at
持久化: ops/schedules.json (atomic + flock)
```

## 2. Schedule 执行 (冻结)
```
run_due_schedules(root, now):
  for s in enabled & due:
    dedup_key = schedule_id + window (5min)
    已执行 → skip (记录 duplicate prevented)
    flock → 更新 next_run_at → health_check(release_id) [S21 复用]
  missed (next_run_at < now - interval): bounded catch-up (≤3) + skipped evidence
Scheduler 不判断健康/不决定 rollback (只 When/What)
```

## 3. Health Projection (冻结, 非第二事实源)
```
project_health(project_id) = f(Releases, HealthChecks, Incidents, Recovery)
  - 最新 check 每 release: HEALTHY/DEGRADED/UNHEALTHY
  - 有 active incident + RECOVERING → RECOVERING
  - 无数据 → UNKNOWN
release_health_history(release_id): checks 按时间序
compare_releases(a, b): 真实数据 (latest result / failures / incidents / recoveries / rollbacks)
```

## 4. Control Plane API
```
GET /api/operations/overview | GET /api/operations/projects | GET /api/projects/{id}/health
GET /api/projects/{id}/health/history | GET /api/releases/{id}/health | GET /api/releases/{id}/health/history
GET /api/releases/compare?release_a=&release_b= | GET /api/schedules
POST /api/schedules | POST /api/schedules/{id}/disable|enable|delete
```

## 5. CLI
```
factory ops status/health/history/incidents/schedules/releases
factory schedule create/list/status/disable/enable/delete
```

## 6. UI: ProductionPage 升级 Control Tower
- Overview 卡片 (计数来自 API)
- Project Health 表 (Multi-Release)
- Release Health Timeline
- Incidents 列表 + Schedule 列表
