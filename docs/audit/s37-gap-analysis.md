# S37 Gap Analysis — Evidence-driven Workforce Learning

> 日期: 2026-08-29 | HEAD: 628b6183 (v1.1.343)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| Experience (S14/S15) | memory/experience.py (TYPES 6 类 + ExperienceRecord) | REAL (Learning 来源) |
| 旧 LearningEngine | memory/learning_engine.py (287 行, 会话时代 Pattern/AgentProfile 学习) | PARTIAL (无生产 Evidence 闭环/无治理) |
| LearningObservation (来自 Production Evidence) | 无 | MISSING |
| LearningHypothesis/Candidate/Result | 无 | MISSING |
| Learning Lifecycle (OBSERVED→…→VALIDATED/REJECTED) | 无 | MISSING |
| Negative Learning (Failure Pattern) | 无 | MISSING |
| ContextFeedback → Learning (S36 消费) | 无 | MISSING |
| Learning Confidence (observed/inferred/validated/unknown) | 无 | MISSING |
| Learning Conflict | 无 | MISSING |
| Learning Plugin (替换测试) | 无 | MISSING |
| Learning Cost 记账 | 无 | MISSING |

## 设计
```
Production Evidence (ProductionRun/Verification/Recovery/Evaluation/ContextFeedback)
→ LearningObservation (source/scope/pattern/success_failure)
→ LearningHypothesis (HYPOTHESIS ≠ Fact)
→ LearningCandidate (STRATEGY/PATTERN/LESSON/PROCEDURE/CONSTRAINT/SUCCESS_PATTERN/FAILURE_PATTERN)
→ Evidence Evaluation (sample_count/success/failure/confidence)
→ VALIDATED / REJECTED / CONFLICT
→ [STOP] (绝不自动进 Production; Promotion = S38)

Lifecycle: OBSERVED→HYPOTHESIS→CANDIDATE→EVALUATING→VALIDATED/REJECTED/SUPERSEDED
Confidence: observed/inferred/validated/unknown (小样本自然降权)
Negative Learning: what fails / why / under which scope
Conflict: evidence/scope/freshness/confidence; 无法 → CONFLICT/UNRESOLVED (非 last-write-wins)
Learning Plugin: type=learning (discovery plugin 化, Core 零修改替换)
Learning Cost: input/output tokens + estimated_cost (cost_type=estimated)
```

## 复用
memory/experience.py + S36 context_feedbacks + S33 performance + S31 Plugin Kernel + S17 governance

## 禁止
- 自动修改 Production/Skill/Plugin/Workflow/Policy/Core (Promotion=S38)
- Conversation/LLM imagination 当 Production Evidence
- last-write-wins 冲突 / 1 次成功 → 高置信度
