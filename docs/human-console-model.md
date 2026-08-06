# Human Console Model

> 日期: 2026-08-06 | 关联: ADR-0034, Phase 11A

## Human Layer 定位

```
Human Layer (Console) = Human Control Center
  不是传统后台管理系统 / 不是替代 Core / 不是业务逻辑层
  Console 只读 Core/Extension 产生的数据, 提供观察/理解/审批/控制入口

Core → Extension → Console
```

## 普通模式 vs 专业模式

```
普通用户看到 (默认, 简单):
  项目 → AI 当前状态 → 需要我决定什么 → 为什么这样推荐

高级用户展开 (专业):
  Provider / Agent / Skill / Cost / Evidence / Event
```

## API (只读, 为 11B Web UI 准备)

```
GET /projects               → id/name/lifecycle stage/status/last activity
GET /projects/{id}/lifecycle → current stage/completed/pending approval/next actions
GET /approvals              → artifact/gate/confidence/risk/evidence/status
GET /decisions/{id}         → options/recommendation/score/reasoning/evidence/risk
GET /recommendations        → candidate/score/factors/explanation
GET /experience             → provider/agent/skill/workflow/success rate/confidence
GET /providers              → capability/cost/performance/experience
(路由函数无 Web 依赖, 未来挂 FastAPI 薄层)
```

## Core 与 Console 边界

```
Console 只能通过: Event/Artifact/Decision/Recommendation/Experience/Approval 读状态
零写操作 (Permission boundary: 无写 API)
不自动执行 / 不自动批准 / 不自动修改 Decision/权重 / 不替代 Human
删除 factory-console → Factory 照常运行
```

## ConsoleDashboard 七域

```
active_projects / pending_approvals / running_agents / recent_decisions
/ cost_summary / experience_summary / activity
```
