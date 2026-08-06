# AI Software Factory — Phase 9a: Product Intelligence 基础

> 日期: 2026-08-06
> 前置: Phase 8B-3 (58ac634, 2883 tests)
> 目标: product/ 基础 — Artifact 抽象 + Approval Gate 抽象 + Workflow 骨架

## 5 点架构约束 (用户确认)

1. **Artifact 抽象**: Artifact 基础模型 (id/type/content/status/created_by/provider_id/agent_id/source_events/version/confidence/created_at); 未来多类型 (Product/Research/PRD/UI/Architecture/Deployment/Operation)
2. **Approval Gate 抽象**: ApprovalGate/ApprovalRequest/ApprovalDecision — 任何 Artifact 可申请; PRD/UI mandatory, Architecture recommended
3. **AI Artifact Lineage**: Input→Agent→Provider→Artifact→Approval (记录 provider_id/agent_id/events/version)
4. **Confidence Model**: confidence 字段 (审核优先级/经验学习/Provider 反馈)
5. **Product Workflow 解耦**: Product Decision Artifact — Idea→Research→PRD→Approval→Product Decision→Architecture→Task→Workflow

## 范围

- factory-core/product/ (models/service/store/events)
- Artifact 抽象 + ProductIdea + Approval Gate 三模型
- ProductWorkflow 骨架 + Product Decision 概念
- Event: idea.*/product.*/approval.*
- CLI: product idea create/list/show + workflow start/status + approval list/decide
- 测试: 新增 ≥60, 2883 不回归
- ADR-0026
