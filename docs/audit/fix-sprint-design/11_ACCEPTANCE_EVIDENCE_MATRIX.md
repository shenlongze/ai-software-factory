# 11 — ACCEPTANCE EVIDENCE MATRIX (STEP11)

| Fix | Static | Runtime | Persistence | E2E | Governance | Regression |
|-----|--------|---------|-------------|-----|------------|-----------|
| FX-01 | exec record 写 path 含 task_ref | 真实执行新记录含 TASK-* | exec records 可见 task_ref | 会话→任务→exec 执行→记录回溯 | audit event | pytest exec 组 |
| FX-02 | execution_plan 写路径禁写 | M3 路径不再产新 | execution_plan.json 无新增 | M3 触发不写 | — | orchestrator 测试 |
| FX-03 | plan 含 requirement_id | 真实计划带 req 引用 | session_plans 可见 | 需求→计划→任务 回溯 | audit | planning 测试 |
| FX-04 | Run 记录挂载字段 | 会话链产物可查 | Run/artifacts 关联 | 执行→产物→审计 | audit | 回归 |
| FX-05 | llm_fn 装配接 policy | selection 非固定默认 | selection audit | 任务→模型选择 | audit event | llm 测试 |
| FX-06 | router 候选含角色 Agent | 角色 Agent 可触发 | records 含角色 | 触发链 E2E | audit | exec 测试 |
| FX-07 | 分析落盘路径 | 分析结果可读 | 报告文件 | 分析→报告 | audit | 测试 |
| FX-08 | 取证报告 | — | — | — | — | — |

禁止以 "代码存在/可调用/测试通过" 为唯一验收 — 必须含 Runtime+Persistence+E2E+Governance 证据
