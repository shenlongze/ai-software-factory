# 03 — DOMAIN MIGRATION IMPACT (STEP11)
> 仅设计影响, 不迁移

| Domain | 当前状态 | Contract 目标 | 变更类型 | 数据影响 | 反向兼容 |
|--------|---------|--------------|---------|---------|---------|
| Requirement | CURRENT (capture) | + 引用契约 | 增加 plan.requirement_id 只读引用 | requirements.json 不变 | 兼容 |
| Planning | CURRENT | 承接 requirement_id | session_plans 增字段 | 新字段可选 | 兼容 |
| Execution Task (backlog) | CURRENT M4 | 保持 SSOT | 无结构变更 (FX-01 只改 exec 侧) | 不变 | 兼容 |
| Runtime (exec) | CURRENT | 引用对齐 | exec 记录写 TASK-* 引用 | exec records 增字段 | 兼容 (旧 T00x 保留历史) |
| Planning 历史 (execution_plan) | M3 历史 | 冻结写入 | 禁写 | 不删数据 | 只读 |
| Artifact | CURRENT (exec) | 会话链关联 | Run 挂 Artifact | 会话链 Run 记录 | 兼容 |
| Verification | PARTIAL | 冻结归属 | 取证后 | — | — |
| Product/PRD | ABSENT | CONTRACT-ONLY | 不建实体 (M3) | 无 | — |
