# S14 Experience & Learning Foundation — Evidence-backed 生产经验证据

> 日期: 2026-08-29 | HEAD: (S14 commit) | v1.1.320

## 架构
```
Production facts (S1-S12) → Evaluation (S13) → Deterministic Extraction → ExperienceRecord
  → ExperienceStore + meta sidecar → Deterministic Retrieval (ACTIVE only) → Future Production
```

## 核心设计
- **Experience ≠ Fact**: ExperienceRecord(复用 memory/experience.py)+ meta sidecar
  (source_production_run_id/source_evaluation_id/evidence_refs/status/success_count/failure_count)
- **确定性提取**: 成功生产 → SUCCESS_PATTERN/DEBUG_EXPERIENCE (ACTIVE); 失败 → FAILURE_PATTERN (CANDIDATE)
- **Confidence 透明公式**: evaluation 30 + verification 30 + lineage 20 + workspace 20 = 100
- **确定性检索**: 关键词 (中文 2-gram + 英文词) + ranking (domain 40/context 30/observation 20/confidence 10), 无 vector
- **Lifecycle**: ACTIVE / SUPERSEDED / INVALIDATED (meta 驱动)
- **Outcome feedback**: success/failure_count + 统计置信度 (一次成功 ≠ 100%)
- **幂等**: 同 production_run → 同 experience

## REAL / SEMI / GAP
| Capability | Status |
|------------|--------|
| Evidence-backed Experience | REAL |
| Contract + 确定性提取 | REAL |
| Persistence + Registry | REAL |
| Lifecycle (ACTIVE/SUPERSEDED/INVALIDATED) | REAL |
| Confidence | REAL |
| 确定性 Retrieval + Ranking | REAL |
| Invalidated/Superseded 过滤 | REAL |
| 幂等提取 | REAL |
| Outcome feedback | REAL |
| CLI + API | REAL |
| Production→Experience→Retrieval E2E | REAL |
| Semantic Vector Retrieval | GAP (故意) |
| LLM Experience Extraction | GAP (故意) |
| Autonomous Learning | GAP (S15+) |

## 测试
```
S14: 12/12 passed
全量 llm + core: 753 passed + 5 skipped (零失败)
```

## Trust Boundary
Experience 永远不能改变 Production/Artifact/Verification status (I8)——只作为 candidate guidance, Verification 保留最终裁决权。
