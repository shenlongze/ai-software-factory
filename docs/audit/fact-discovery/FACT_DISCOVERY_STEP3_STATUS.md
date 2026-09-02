# STEP 3 最终回答 — 能力分层 (2026-09-02)

## 1. 代码存在 (CODE EXISTS) — 无法证明运行时使用
- LLMRouter (llm_router.py, 消费 0)
- factory-core 全部 (console→core=0)
- factory-runtime 全部 (无运行痕迹)
- PRD/Release/Learning 结构化实体 (未定位)

## 2. 可调用 (CALLABLE)
- exec 7 角色 Agent (developer/pm/architect/tester/release/uxui, agents.json 注册)
- 371 API 端点 (静态存在, 未逐端点触发)

## 3. 进入生产路径 (PRODUCTION_USED)
- console 会话链 (agent_loop: execute_plan/chain_next/ExecState/reconcile) — 本轮 E2E 验证
- llm_fn 注入调用 (全模块, console_sessions.py:104 llm_raw)
- requirements.json 写读 (agent_loop:795 / fastapi:1501)
- exec 6 集成点 (service.py:412-818: runtime_session/agent_executor/AgentRuntime/tool/skill/mcp)

## 4. 真实运行证据 (RUNTIME_EXECUTED)
- Agent 执行 (execution_records 100 条, backend-1 48/flutter-dev 17, 87 success)
- Artifact (exec/results.json patches, ART-xxx)
- Audit (5160 事件) / 会话 (81) / 经验 (84)
- 执行链投影 (6 session_exec)
- LLM usage 记录 (providers/usage.json)
- Requirement 7 条 VALIDATED

## 5. 持久化事实 (PERSISTED)
- requirements.json / console_sessions / audit_events / exec 全套 /
  session_plans / session_exec / agents / skills / memory / org projects

## 6. 验证证据 (VERIFIED)
- 会话链 Plan→Task→ExecState→聚合 (本轮多轮 E2E, 1049+ tests)
- Requirement/Plan/Task 关联 (requirements.json + plan_id + backlog)

## 7. 完全闭合链路
- User → 会话 → Plan → Task → ExecState → Run → 回写 → reconcile (会话链)
- Requirement → requirements.json → (读取 API)

## 8. 断裂链路
- Requirement → PRD → Plan: PRD 实体未定位
- Requirement 分析 (product_intelligence) → 持久化: 不落盘
- 会话链 → factory-core: 零
- LLMRouter → 生产: 零

## 9. 无 production consumer 模块
- factory-core (console 侧) / factory-runtime / LLMRouter / PRD 层

## 10. UNKNOWN
- exec 角色 Agent 触发入口 / factory.db 用途 / core 是否有独立数据 /
  371 API 未触发部分 / Release/Learning 运行时
