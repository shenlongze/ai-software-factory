# ORCHESTRATION REALITY — STEP 7

| 维度 | 会话链 | 证据 |
|------|--------|------|
| Capability Selection | 固定 (意图→动作注册表) | fastapi 意图路由 |
| Agent Selection | 动态 (gateway router classify+score) | router.py:193 |
| Model Selection | 固定默认 | _default_llm_fn |
| Task Planning | LLM 生成 (结构固定 tasks/order) | plan_development |
| Task Scheduling | 动态依赖门控 | ExecState.next |
| Execution Orchestration | 单任务串行推进 | chain_next |
| Recovery | 动态 (Run 证据) | ExecState.recover |
| Replan | 无 (会话链) | G-REPLAN-01 |

## 判定: HYBRID
- 执行层: 动态 (依赖调度+Agent 路由+恢复) = M4
- 规划层: 半动态 (LLM 内容动态, 模板结构固定)
- 模型层: 静态 (无路由)
- 生命周期: 固定链 (plan→approve→task→exec→reconcile)
