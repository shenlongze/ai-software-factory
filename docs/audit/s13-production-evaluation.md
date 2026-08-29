# S13 Production Evaluation — 确定性质量评价证据

> 日期: 2026-08-29 | HEAD: (S13 commit) | v1.1.319

## 评价模型
```
ProductionRun facts (node_runs/artifacts/attempts/verification/history)
  → Deterministic Evaluator (非 LLM)
  → ProductionEvaluation Artifact (evaluations/<run_id>.json)
```

## 维度权重 (透明)
| 维度 | 权重 |
|------|------|
| completion | 20 |
| artifact_integrity | 15 |
| verification | 20 |
| lineage_integrity | 20 |
| workspace_delivery | 15 |
| repair_efficiency | 10 |
| **Total** | **100** |

## 历史失败识别 (核心)
对于 FAIL→Repair→PASS 生产:
- final_status = COMPLETED (历史 FAIL 不判最终 FAIL)
- historical_failures = 1
- repair_count = 1 (FAIL→PASS 序列检测)
- repair_efficiency = 80 (1 repair = acceptable)

## 失败生产识别
- completion = FAIL (0 分)
- overall_score < 50 (显著低于成功生产)

## 幂等 + 可重复
- 同 evidence → 同 score (force=True 重算完全一致)
- 重复 evaluate → 返回现有 (evaluation_id 相同)

## REAL / SEMI / GAP
| Capability | Status |
|------------|--------|
| Evidence collection | REAL |
| Completion / Artifact / Verification / Lineage / Workspace / Repair 评价 | REAL |
| Deterministic score | REAL |
| Evaluation Artifact 持久化 | REAL |
| CLI (factory production evaluate) | REAL |
| API (GET /api/production-runs/{id}/evaluation) | REAL |
| Idempotency / Reproducibility | REAL |
| LLM subjective evaluation | GAP (故意) |
| Experience learning | GAP (S14) |

## 测试
```
S13: 12/12 passed
全量 llm + core: 741 passed + 5 skipped (零失败)
```
