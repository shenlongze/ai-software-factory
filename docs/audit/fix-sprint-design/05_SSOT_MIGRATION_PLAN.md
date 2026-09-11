# 05 — SSOT MIGRATION PLAN (STEP11)

| Entity | 当前 SSOT | Contract SSOT | 变更 | Write Owner |
|--------|----------|--------------|------|-------------|
| Task | backlog TASK-* | backlog TASK-* (不变) | 无 | ManagementStore |
| Task (exec 侧) | exec T00x (独立) | 降为 ExecutionRecord (引用 TASK-*) | FX-01 | exec store (记录) |
| Task (execution_plan) | T-* (可写) | 历史冻结 (不写) | FX-02 | 无 (禁写) |
| Plan | session_plans | session_plans (+requirement_id 引用) | FX-03 | PendingPlanStore |
| Run | gateway registry / EXS-* | 分层冻结: Run=registry, Record=EXS | FX-01/04 | gateway / exec |
| Artifact | exec results | Run/Record 持有 | FX-04 | exec/gateway |
| Verification | 分裂 (exec results + ExecState.verify) | 取证后冻结 (D 类) | FX-08 | 待定 |
| Model Selection | 无 (LLMRouter 0 消费) | Policy→Selection (治理链) | FX-05 | 待定 (policy owner) |
