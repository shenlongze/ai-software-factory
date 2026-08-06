# AI Software Factory — Phase 10A-4: Experience Integration + TaskEvaluation

> 日期: 2026-08-06
> 前置: Phase 10A-3 (5e2c61f, 3803 tests)
> 目标: 经验闭环 — 任务→能力→执行→结果→经验→推荐优化 (经验分析, 非自我修改)

## 范围

- experience.py 增强 (ExperienceRecord 全字段 + ExperienceAnalyzer effective score + 30 天半衰期)
- evaluate.py 新增 (TaskEvaluator: TaskRequirement → TaskEvaluation)
- Recommendation 集成 (Experience 影响评分, 不覆盖真实能力, 冷启动 0.5, 正负经验)
- 负经验机制 (Failure Experience: negative_signal)
- Feedback Loop 事件
- CLI: intelligence experience list + intelligence evaluate
- docs/experience-learning-model.md + ADR-0033
- 测试: 新增 ≥100, 3803 不回归

## 禁止 (未来 Self Evolution 单独设计)

自动修改权重 / 自动生成 Skill / 自我复制 Agent / 自动重构 Core
