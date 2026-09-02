# 02 — DOMAIN MODEL FREEZE (STEP 10, 2026-09-02)

> 12 个正式 Domain。状态: CURRENT=现有生产域 / CONTRACT-ONLY=契约冻结(无实体) /
> FUTURE=未来里程碑 (不视为缺陷)

| # | Domain | Status | Primary Entity | Purpose |
|---|--------|--------|----------------|---------|
| 1 | Requirement Domain | CURRENT (capture) | Requirement (req_*) | 需求捕获/验证/持久化 |
| 2 | Product/PRD Domain | CONTRACT-ONLY (实体 ABSENT, M3) | PRD (未来 prd_*) | 结构化产品承诺 |
| 3 | Planning Domain | CURRENT | Plan (PLAN-*) | 计划事实 + 生命周期 |
| 4 | Execution Task Domain | CURRENT | Task (TASK-*, backlog) | 生产执行任务事实 |
| 5 | Runtime/Run Domain | CURRENT | Run | 一次运行事实 |
| 6 | Execution Record Domain | CURRENT (exec 域) | ExecutionRecord (EXS-*) | 执行过程事实 |
| 7 | Artifact Domain | CURRENT (exec 域) | Artifact (ART-*) | 产物事实 |
| 8 | Verification Domain | PARTIAL (exec results) | Verification | 验证事实 |
| 9 | Agent Domain | CURRENT | Agent (backend-1 等) | 执行能力注册/选择 |
| 10 | Model/LLM Control Domain | PARTIAL | Model/Provider | 调用真实/选择契约冻结 |
| 11 | Project Domain | CURRENT | Project (P-*) | 项目/backlog/sprint |
| 12 | Audit/Governance Domain | CURRENT | Audit Event | 不可变治理记录 |

## 未定义为新 Domain (证据不足, 禁止自行创造)
- Intent (投影于消息) / ExecState (投影) / Skill / Tool — 挂靠各自 Domain, 非独立 SSOT Domain
