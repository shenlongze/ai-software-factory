# 02 — FIX SCOPE MATRIX (STEP11)
> 每个 Fix: 最小范围, 无代码 (设计级)

| Fix ID | GAP | 目标 Contract | Domain | 当前 | 目标 | 影响面 | 验收 |
|--------|-----|--------------|--------|------|------|--------|------|
| FX-01 | G-TRUTH-01 (exec 对齐) | 06 Execution Truth | Runtime/Exec Record | exec T00x 独立 | exec 记录引用 backlog TASK-* ID | exec store 写路径 | 无 T00x 新平行; 记录可回溯 TASK-* |
| FX-02 | G-TRUTH-01 (execution_plan 冻结) | 06 Execution Truth | Planning(历史) | execution_plan 可写 | 冻结写入 (只读/标记 historical) | orchestrator/actions M3 路径 | execution_plan 不再产生新 Task 事实 |
| FX-03 | G-REQ-01/G-REQ-03 | 07 Contract (D-4 C) | Requirement→Plan | requirements.json 无下游 | plan 携带 requirement_id 引用 (只读引用) | session_plans/execute_plan | 需求→计划可追踪 (ID 引用) |
| FX-04 | G-ART-01 | 03 Task Contract (D-6) | Runtime→Artifact | 会话链无 artifact 关联 | Run/Record 挂 Artifact/Verify, Task 经 Run 可达 | 会话链 Run 记录 + exec results | Task→Run→Artifact 审计链 |
| FX-05 | G-LLM-01 | 09 Model Selection (D-8) | Model Control | LLMRouter 消费 0 | Task/Agent→Policy→Selection 进治理链 | llm_fn 装配点 + LLMRouter | 模型选择有 policy + audit |
| FX-06 | G-AGENT-01 (触发验证) | 08 Agent Selection (D-7) | Agent | 角色 Agent 触发 UNKNOWN | 验证/建立生产触发入口 | gateway router + exec | 角色 Agent 生产调用链可见 |
| FX-07 | G-REQ-02 | 07 Contract | Product Intelligence | 分析不落盘 | 分析结果持久化 (可审计回看) | product_intelligence action | 分析报告落盘 + audit |
| FX-08 | G-VER-01 (验证 SSOT) | 待冻结 (D 类) | Verification | exec results + ExecState.verify | 冻结 Verification SSOT 归属 (Run/Record) | 取证后定 | 取证后定 |

## 依赖
FX-04 依赖 FX-01 (Run ID 稳定) / FX-05 依赖 FX-01 (Task capability) / FX-03 独立 /
FX-02 独立 (历史冻结) / FX-06 依赖 FX-01
