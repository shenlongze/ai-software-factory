# S22 Gap Analysis — Continuous Production Operations & Control Tower

> 日期: 2026-08-29 | HEAD: cfad0c1a (v1.1.328)

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| Health Monitor (5 deterministic checks) | health_service.py | REAL |
| Health Incident (OPEN/RECOVERING/RESOLVED/FAILED) | health_service.py | REAL |
| Automatic Recovery (经 rollback_service) | health_service.py | REAL |
| Rollback / Verification / Integrity | S19/S20/S20.5 | REAL |
| Release (project_id 关联) | release_service.py | REAL |
| session/scheduler.py (M3c 任务调度) | session/scheduler.py | LEGACY (消费 plan.json, 与健康调度无关, 不复用) |

## MISSING (S22 新增)
| GAP | 最小实现 |
|-----|---------|
| Schedule Contract + 持久化 (schedule_id/project_id/release_id/interval/enabled/next_run_at) | ops_scheduler.py |
| Schedule 执行循环 (到期 → health_check; 不拥有业务逻辑) | ops_scheduler.py |
| Missed schedule (bounded catch-up + skipped evidence) | ops_scheduler.py |
| Schedule 幂等/并发 (dedup key: schedule_id+window; flock) | ops_scheduler.py |
| Health State Projection (facts → HEALTHY/DEGRADED/UNHEALTHY/RECOVERING/UNKNOWN, 非第二事实源) | ops_projection.py |
| Health History (真实 persisted checks/incidents/recovery) | ops_projection.py |
| Multi-Release Health + Comparison (真实数据比较) | ops_projection.py |
| Control Plane API + CLI | fastapi_adapter + cli_factory |
| Control Tower UI (升级 ProductionPage) | ProductionPage.tsx |

## 设计
```
Schedule(persisted) → 到期 → health_check(release) [dedup+lock]
  → HealthCheck facts → Incident (S21) → recover (S21 rollback)
  → Health Projection (facts 计算, 可重建, 非唯一真相)
Control Plane: projects/releases/health/history/incidents/schedules 聚合投影
```

## 禁止
- Scheduler 自己判断健康/决定 rollback / UI 计算健康 / 第二事实源 / 无限 catch-up / runaway recovery
