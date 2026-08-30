# S23 Gap Analysis — Production Intelligence & Root-Cause Intelligence

> 日期: 2026-08-29 | HEAD: 611be69b (v1.1.329)

## EXISTING (复用)
| 能力 | 位置 | 状态 |
|------|------|------|
| Production Facts (Incident/HealthCheck/Release/Rollback/Verification) | S18-S22 | REAL |
| Experience (extract/retrieve/lineage) | production_experience.py (S14/S15) | REAL |
| Governance (approval) | governance_service.py (S17) | REAL |
| Recovery Policy (S21 自动 rollback) | health_service.py | REAL |
| memory/recommendation.py (旧 M 层推荐) | memory/recommendation.py | LEGACY (非生产 RCA, 不复用) |

## MISSING (S23 新增)
| GAP | 最小实现 |
|-----|---------|
| Production Intelligence Contract (analysis_id/type/status/evidence_refs) | production_intelligence.py |
| Signal Extraction (facts → signals, 带 source_ref) | production_intelligence.py |
| Temporal Correlation (release→health→incident 时间关系) | production_intelligence.py |
| RootCauseCandidate (category/confidence/evidence/supporting/contradicting) | production_intelligence.py |
| Evidence Weighting (deterministic: verification > health > correlation > pattern > experience) | production_intelligence.py |
| Historical Pattern Detection (相似 incidents) | production_intelligence.py |
| Recommendation Contract (type/risk/requires_approval/status) | production_intelligence.py |
| Recommendation Lineage + Outcome (decision/action/outcome) | production_intelligence.py |
| Hallucination Protection (evidence_ref 不存在 → reject) | production_intelligence.py |
| Intelligence Store (analysis 持久化 + re-analysis 不覆盖) | production_intelligence.py |
| CLI/API/UI | cli_factory + fastapi_adapter + ProductionPage |

## 设计
```
facts (incident/health/release/verification/experience)
  → Signal Extraction (signal_id/source_ref/value)
  → Temporal Correlation (events 时间序)
  → RootCauseCandidates (deterministic evidence weighting + 反证)
  → Recommendations (risk + requires_approval, 经 Governance 决策)
  → Outcome 回写 (lineage)
Intelligence 只 READ/ANALYZE/RECOMMEND, 不 MUTATE (不直接 rollback)
```

## 禁止
- LLM 自由输出当事实 / correlation=causation / recommendation=action / 假 evidence / 覆盖旧 analysis
