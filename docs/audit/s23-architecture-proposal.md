# S23 Architecture Proposal — Production Intelligence & Root-Cause Intelligence

> 日期: 2026-08-29 | 状态: PROPOSAL (Contract Freeze 前)

## 1. Intelligence Contract (冻结)
```
AnalysisRecord: analysis_id / incident_id / release_id / project_id / analysis_type /
  status(REQUESTED/COLLECTING/ANALYZING/COMPLETED/FAILED) / signals[] / findings[] /
  root_cause_candidates[] / recommendations[] / evidence_refs[] / created_at / completed_at
```

## 2. Signal Extraction (冻结)
```
signal: signal_id / signal_type / source_ref / timestamp / value
从 Incident/HealthCheck/Release/Verification/Experience 提取
```

## 3. Temporal Correlation (冻结)
```
事件时间序: release_at → health_degraded_at → incident_at → verification_fail_at
→ correlation evidence (观察, 非因果)
```

## 4. RootCauseCandidate (冻结)
```
candidate_id / category / confidence / evidence_refs / supporting_signals /
contradicting_signals / status(SUPPORTED/POSSIBLE/WEAK/REJECTED)
```

## 5. Evidence Weighting (冻结, deterministic)
```
verification(1.0) > health(0.8) > correlation(0.6) > historical_pattern(0.4) > experience(0.3)
confidence = 加权支持 - 反证惩罚 (可解释)
```

## 6. Recommendation (冻结)
```
recommendation_id / analysis_id / type / priority / confidence / risk(LOW/MED/HIGH) /
requires_approval / evidence_refs / status(PENDING/APPROVED/REJECTED/EXECUTED/EXPIRED) / outcome
Recommendation ≠ Action (经 Governance → 现有 Production Core)
```

## 7. Intelligence Store
```
persisted: ops/intelligence/analyses.json + recommendations.json (append-only)
re-analysis → 新 analysis_id (不覆盖)
```

## 8. Hallucination Protection
```
evidence_ref 校验: 不存在 → finding/recommendation REJECTED (不持久化为 trusted)
```

## 9. CLI/API
```
factory intelligence analyze <incident> | show <id> | root-cause <incident> | recommendations <incident> | evidence <id> | history
POST /api/intelligence/analyses | GET /api/intelligence/analyses/{id}
GET /api/incidents/{id}/analysis | GET /api/incidents/{id}/root-causes | GET /api/incidents/{id}/recommendations
GET /api/intelligence/{id}/evidence | POST /api/recommendations/{id}/decide
```
