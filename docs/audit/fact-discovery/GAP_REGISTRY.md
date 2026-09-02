# GAP REGISTRY — STEP 5 (2026-09-02)

> 每个 GAP = EXPECTED CONTRACT (可证明的系统契约意图) vs ACTUAL FACT (STEP 1-4 证据) 的可证明差异。
> Severity: BLOCKER/CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL (无 P0/P1/P2)

| GAP-ID | Capability | Expected Contract | Actual Fact | 分类 | Severity | 证据 |
|--------|-----------|-------------------|-------------|------|----------|------|
| G-REQ-01 | Requirement Traceability | 需求可追踪到 Plan/Task/执行 | requirements.json 无 plan/task 引用 (仅 project/session/title) | TRACEABILITY_GAP | CRITICAL | requirements.json 7 条 + agent_loop.py:795 |
| G-PRD-01 | PRD Domain | 需求→PRD→Plan 结构化传递 | PRD 实体不存在 (文档/模板有, domain entity 无) | DOMAIN_GAP | CRITICAL | STEP4 PRD forensic ABSENT |
| G-TRUTH-01 | Execution SSOT | 单一 execution truth | 三套: backlog TASK-* / execution_plan T-* / exec T00x (ART-* 引 T00x) | SSOT_GAP | CRITICAL | STEP4 EXECUTION_RELATION |
| G-ART-01 | Artifact Traceability | Task→Run→Artifact→Verification 全链 | 会话链 Task 无 artifact_ref; Artifact 仅 exec 域 (ART-*→T00x) | TRACEABILITY_GAP | HIGH | exec/results.json + backlog 无关联 |
| G-LLM-01 | LLM Control | 模型/Provider 动态选择+fallback+审计 | LLMRouter 消费=0; 实际=provider._default_llm_fn 固定默认 | CONTROL_PLANE_GAP | HIGH | llm_router.py:107 + 消费 0 |
| G-CORE-01 | factory-core Integration | core 领域被生产消费 | 全仓外部引用 0 | INTEGRATION_GAP | HIGH | grep 全仓 0 |
| G-OS-01 | OS Unification | 统一 OS (共享 SSOT/Event/执行) | 5 模块: console+org+exec 集成; core/runtime 孤立; 三套 task 域 | SSOT_GAP | HIGH | STEP4 MODULE_INTEGRATION |
| G-REQ-02 | Requirement Analysis | 需求分析产物持久化可追踪 | product_intelligence 返回 markdown 不落盘 (仅 Audit event) | PERSISTENCE_GAP | MEDIUM | actions.py:2864-2893 |
| G-EXP-01 | Experience Loop | Experience→Learning→Future Decision | experience_store 84 条写入; consumer 未证明 | RUNTIME_GAP | MEDIUM | experience_store + consumer 0 |
| G-LEARN-01 | Learning/Release | Learning/Release 生产闭环 | 端点存在, 持久化/消费者 UNKNOWN | RUNTIME_GAP | MEDIUM | 端点存在 |
| G-VER-01 | Verification Closure | 验证结果→Task/Artifact 一等关联 | verify 在 ExecState/exec results; 无独立 Verification SSOT 下游 | TRACEABILITY_GAP | MEDIUM | exec test_result |
| G-OBS-01 | Observability | 全部关键事实 durable evidence | 部分执行器内部仅 log (非 durable) | OBSERVABILITY_GAP | LOW | 执行器输出 |
| G-REQ-03 | Requirement Version | 需求版本化/变更传播 | requirements.json 无 version/change 字段 | DATA_GAP | MEDIUM | requirements.json 结构 |
| G-AGENT-01 | Agent Control Plane | OS 级 Agent 动态选择 | gateway router 局部选择真实; exec 角色 Agent (dev/pm) 生产入口 UNKNOWN; 7 角色注册但调用链部分 UNKNOWN | CONTROL_PLANE_GAP | HIGH | AGENT_CONTROL_FORENSICS |
| G-REPLAN-01 | Replanning | 失败/变更→动态重规划 | M3 replanner 存在; 会话链无 replan 集成 | ORCHESTRATION_GAP | MEDIUM | orchestrator replanner |
