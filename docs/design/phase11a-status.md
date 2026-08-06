# AI Software Factory — Phase 11A: Human Console Backend API Layer

> 日期: 2026-08-06
> 前置: Phase 10A-4 (d424053, 3918 tests)
> 目标: Human Layer 产品入口 — 统一只读 API (为未来 Web UI 11B 准备)

## 架构

```
Core → Extension → Console (Human Layer, 新增)
factory-console/ 独立目录 (不污染 factory-core)
Console 只读: Event/Artifact/Decision/Recommendation/Experience/Approval
```

## 范围

- factory-console/api/ (projects/lifecycle/approvals/decisions/intelligence/providers) + models/service/events
- 只读 API: /projects /projects/{id}/lifecycle /approvals /decisions/{id} /recommendations /experience /providers
- ConsoleDashboard 模型 (active_projects/pending_approvals/running_agents/recent_decisions/cost_summary/experience_summary)
- Event: console.viewed/approval.opened/dashboard.viewed
- docs/human-console-model.md (普通/专业模式 + Core/Console 边界) + ADR-0034
- 测试: 新增 ≥80, 3918 不回归

## 禁止

Core 修改 / 自动执行 / 自动批准 / 自动修改 Decision/权重 / 替代 Human / React/Vue (11B)
