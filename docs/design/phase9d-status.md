# AI Software Factory — Phase 9d: Product Lifecycle Orchestration

> 日期: 2026-08-06
> 前置: Phase 9c (ebcbbf2, 3263 tests)
> 目标: Idea→Research→PRD→Approval→UI→Architecture→Task→Development 可暂停可恢复可扩展生命周期

## 范围

- Stage Registry (ProductStageRegistry, 支持多 lifecycle 类型)
- Product Workflow Template (声明式: software_project 模板)
- Decision Artifact 链 (Product Decision → Architecture Decision → Task Plan)
- Task Integration (复用 Task/Workflow Core, 禁修改)
- Lifecycle Events (lifecycle.started/stage.entered/stage.completed/decision.created/lifecycle.completed)
- Dashboard Product Lifecycle View
- 测试: 新增 ≥100, 3263 不回归
- ADR-0029

## 冻结约束

Core 零修改 / Extension only / Event 唯一事实源 / Artifact lineage / Approval & Provider Intelligence 复用 / 禁止复制 Workflow Core
