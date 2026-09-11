# 04 — RELATION MIGRATION PLAN (STEP11)

| Relation | 现状 | Contract 目标 | 变更 |
|----------|------|--------------|------|
| Requirement → Plan | ABSENT | requirement_id 引用 | FX-03: plan 创建时记录来源 req (只读) |
| Plan → Task | PROVEN | 保持 | 无 |
| Task → Run | PROVEN (会话链) | 保持 | 无 |
| Task → Run (exec) | UNKNOWN (T00x 无 TASK-* 映射) | exec Run 引用 TASK-* | FX-01 |
| Run → ExecutionRecord | PROVEN (exec) | 保持 | 无 |
| Run → Artifact | PROVEN (exec) / ABSENT (会话链) | Run 统一挂载 | FX-04 |
| Run → Verification | PARTIAL | Run 统一挂载 | FX-04 |
| Task → Capability Constraint | CONTRACT-ONLY | 语义实现 | FX-05/06 |
| Task/Agent → Model Policy | CONTRACT-ONLY | 治理链 | FX-05 |
| 核心 → Audit | PROVEN | 保持 | 无 |
