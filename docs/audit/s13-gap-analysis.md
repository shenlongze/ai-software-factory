# S13 Gap Analysis — Production Evaluation & Evidence Intelligence

> 日期: 2026-08-29 | HEAD: fa99beb8 (v1.1.318)

## Existing REAL Evidence (Evaluation 输入)
| 事实 | 位置 |
|------|------|
| ProductionRun state/node_runs/artifacts/history | production_run.py |
| NodeRun attempts/verification/failure_reason | node_runtime.py |
| Artifact lifecycle state/producer/payload | artifact_lifecycle.py |
| Handoff refs (from/to/artifacts) | agent_kernel.py |
| Repair attempts (attempts[].verification FAIL→PASS) | node_runtime.py (S5/S12) |

## Missing (S13 新增)
| GAP | 最小实现 |
|-----|---------|
| ProductionRun 级 Evaluation | production_evaluation.py: 确定性评分 (非 LLM) |
| Evaluation Artifact 持久化 | evaluations/<run_id>.json (幂等) |
| CLI/API | factory production evaluate + GET /api/production-runs/{id}/evaluation |

## 设计
- 评分 = 加权和 (completion 20 / artifact_integrity 15 / verification 20 / lineage 20 / workspace 15 / repair 10)
- 同一 evidence → 同一 score (可重复)
- 历史 FAIL 不判最终 FAIL (final_status + historical_failures 分开)
- Evaluation 是 derived intelligence, 不建第二事实源

## 禁止
- LLM 打分 / session memory / 重建 Event Store / 覆盖 Production facts
