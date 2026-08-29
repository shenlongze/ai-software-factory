# S14 Gap Analysis — Experience & Learning Foundation

> 日期: 2026-08-29 | HEAD: cb58ac30 (v1.1.319)

## Existing REAL (复用)
| 基础设施 | 位置 | 状态 |
|----------|------|------|
| ExperienceRecord 模型 (id/type/context/problem/action/result/confidence/source) | memory/experience.py | REAL |
| ExperienceStore (add/get/records/stats + 持久化) | memory/experience_store.py | REAL |
| LearningEngine / PatternLearner | memory/learning_engine.py | REAL |
| Production Evaluation (S13) | production_evaluation.py | REAL |
| Production facts (S1-S12) | production_run/node_runtime/artifact | REAL |

## Missing (S14 桥接层)
| GAP | 最小实现 |
|-----|---------|
| Production Evidence → Experience 确定性提取 | production_experience.py: extract(root, production_run_id) |
| Evidence-backed confidence | 公式: evaluation 30 + final_verification 30 + lineage 20 + workspace 20 |
| 幂等提取 | 同 production_run_id → 同 experience (检查已存在) |
| 确定性 retrieval | domain/context 关键词匹配 + ranking (无 vector) |
| Active 过滤 | ACTIVE 可检索, SUPERSEDED/INVALIDATED 排除 |
| Outcome feedback | record_outcome: success/failure count + confidence 更新 |

## 设计
- Experience = derived knowledge (带 evidence_refs/source_production_run_id/source_evaluation_id)
- 成功生产 → ACTIVE; 失败生产 → CANDIDATE (非推荐)
- Experience 永远不能改变 Production/Artifact/Verification status (I8)
- 不建 vector/RAG/embedding (GAP 留 S15+)

## 禁止
- Chat/Session Memory / raw prompt / LLM 自评经验 / 无证据经验
