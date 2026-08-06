# AI Software Factory — Phase 10A-2: Decision Intelligence

> 日期: 2026-08-06
> 前置: Phase 10A-1 (49b06f2, 3568 tests)
> 目标: 决策链 — 分析→选项→评分→推荐→证据→风险→Approval (非 AI 自动执行/非 LLM 接入)

## 范围

- intelligence/decision.py (DecisionIntelligence: Context→Analysis→Options→Evaluation→Recommendation→Risk→Decision)
- 新模型: DecisionOption/DecisionAnalysis/DecisionResult
- 规则评分 (Capability+Cost+Performance+Experience 每项 0-1 + reasoning, 不绑定 LLM)
- Approval 集成 (复用 9c; 高风险 required_approval, 不建新状态机)
- Evidence Chain (六来源, 禁无证据推荐)
- Event: analysis.started/completed + option.evaluated + decision.created
- CLI: intelligence decision create
- docs/decision-intelligence-model.md + ADR-0031
- 测试: 新增 ≥80, 3568 不回归

## 禁止 (后续 Phase)

Recommendation Engine (10A-3) / Experience 学习 (10A-4) / LLM 调用 / 自动执行
