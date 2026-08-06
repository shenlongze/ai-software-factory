# AI Software Factory — Phase 10A-3: Recommendation Engine

> 日期: 2026-08-06
> 前置: Phase 10A-2 (f60e972, 3666 tests)
> 目标: 智能推荐核心 — "专业的人做专业的事" (多因素评分 + 解释 + 不自动执行)

## 范围

- intelligence/recommend.py (RecommendationEngine: Context → 多因素评分 → 解释 → Recommendation)
- 评分: Final = Capability×0.35 + Performance×0.30 + Cost×0.20 + Experience×0.15 (权重配置化)
- Candidate 统一抽象 (provider/agent/skill/workflow)
- Experience 集成 (effective = score×confidence×freshness; 冷启动中性)
- Decision 集成 (复用 10A-2: Recommendation → Decision → Approval)
- 4 事件 + CLI (intelligence recommend)
- docs/recommendation-engine-model.md + ADR-0032
- 测试: 新增 ≥80, 3666 不回归

## 禁止 (10A-4)

自动学习 / 自动优化权重 / 自我修改 / LLM 调用
