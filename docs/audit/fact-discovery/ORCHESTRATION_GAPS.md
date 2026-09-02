# ORCHESTRATION GAPS — STEP 5
- 会话链: 动态成分真实 (ExecState 依赖门控 + gateway agent route + recover)
  - 但: 任务生成固定模板 (plan_development tasks/order), 工具固定 _fc 枚举, 模型固定默认
- M3: orchestrator + replanner 存在, 生产消费者 (会话链) UNKNOWN
- G-REPLAN-01 MEDIUM: 失败后 replan 在会话链无集成 (FAILED→人工 retry, 无自动 replan)
- 分类: ORCHESTRATION_GAP
- 证据: ORCHESTRATION_FORENSICS.md
