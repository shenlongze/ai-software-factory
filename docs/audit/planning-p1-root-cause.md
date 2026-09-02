# PLANNING-P1-ROOT-CAUSE — Idea → Plan 断裂

> 日期: 2026-09-01 | 状态: P1 OPEN (审计完成, 等 FIX 指令)

## 1. 真实调用链 (E2E 复现)

```
用户: "请调用 plan_development 工具为项目 P-00055f65 制定开发计划..."
POST /api/sessions/{sid}/messages (无 stream=1)          ← 同步路径
→ parse_intent_llm (fastapi_adapter.py:7304)             ← LLM 意图分类
→ intent = project_action / create_task                  ← 无 plan_development 选项!
→ 标准意图路由分支 (create_task 7308 / project_action 7586)
→ service.create_task × 1 (垃圾任务) 或 send_message 文本
→ LLM 文本声称 "计划已生成, 6 个任务..."                  ← 无工具调用
→ Execution Truth validator 标注 "没有真实工具执行记录"    ← 正确拦截, 但链已断
→ 无 pending_plan / 无 plan_id / 无 plan.json
```

## 2. 失败调用链 (代码级)

### 2.1 意图枚举缺 plan_development

`query_engine.py:596-637` parse_intent_llm 的 intent 白名单:

```python
"list_projects|project_status|project_scan|project_quality|project_tasks|..."
"deep_analyze", "task_action", "create_idea", "project_artifacts", "monitor",
"git_push", "project_action", "create_idea"   ← 无 "plan_development"
```

"制定开发计划 / 生成计划 / 规划项目" 无对应 intent → LLM 分类器
落到最近的 create_task / project_action / 未分类。

### 2.2 标准意图路由无 plan_development 分支

`fastapi_adapter.py` 同步路径 (7163-7742):
- project 分支 → run_agent v1
- company 分支 → 标准意图路由 (create_task/create_idea/project_action/deep_analyze/monitor...)
- 兜底 → run_agent_native (7742, 有 plan_development 工具但只在 LLM 自主调用时)

标准意图路由**没有** plan_development intent 分支 → Planning 请求
被 create_task/project_action 拦截 → 无 Plan 创建。

### 2.3 plan_development 能力真实存在但不可达

- `agent_loop.py:358 plan_development(goal, detail, llm_fn)` → 生成结构化计划
- `agent_loop.py:747` dispatch 调用 → 返回 plan
- `agent_loop.py:833-838` PendingPlanStore 持久化 → session_plans.json (key=session_id)
- `agent_loop.py:2437 PendingPlanStore` 类 (save/get/clear)
- 但**只有 stream 路径的 run_agent_native LLM 工具调用才能触发**
- 同步路径意图路由不提供该能力 → E2E (同步) 永远到不了

## 3. Intent 分类证据 (E2E)

```
meta.intent = "create_task" / "project_action" (5 轮全部)
tool_calls = 0
session_plans.json: 无该会话计划
项目 lifecycle: idea (execute_plan 未触发)
```

## 4. 最小修复边界 (等 FIX 指令)

```
1. query_engine.py parse_intent_llm 白名单 + _INTENT_RULES 增加 plan_development
   (制定开发计划/生成计划/规划项目/计划卡片/开发计划/plan_development)
2. fastapi_adapter.py 同步路径新增 plan_development intent 分支:
   - 调 agent_loop.plan_development (真实 LLM 生成计划)
   - PendingPlanStore.save (persist plan_id/tasks/order/status=pending)
   - 返回 plan 摘要 + plan_id + "待审批" (facts 驱动, 非 LLM 文本声称)
   - 不创建最终 Task (Plan ≠ Task, 等审批)
3. 审批路径已存在: pending_plan 恢复 (811-825) + execute_plan (834)
   → 复用现有 Task Orchestration (dependency/DAG/Schedule/Execution)
4. Execution Truth 不变: plan facts (plan_id/tasks/status) 作为真实证据,
   允许 "已生成包含 N 个任务的计划, 等待审批"; persistence 失败 → NOT_EXECUTED
```

## 5. 影响

- 用户 "规划项目并开发" → 只能得到文本计划, 无法进入真实 Task/DAG/Execution
- 完整生产链 (Idea→Plan→Task→DAG→Schedule→Execution→Truth) 断裂在 Idea→Plan
- Execution Truth 正确拦截虚假声称 (无工具记录) — 非 Truth 问题, 是 Intent Routing 缺陷

## 6. 测试计划 (FIX 后)

- A: "制定开发计划" → intent=plan_development + pending_plan 持久化
- B: "创建任务" → create_task (不误伤)
- C: "制定开发计划并生成 6 个任务" → plan_development (非 create_task×6)
- D: "请调用 plan_development 工具" → 真实工具调用
- E/F: 生成/持久化失败 → 不声称成功
- G/H: 未批准/拒绝 → 不创建 Task
- I/J: SSE/fallback → 单 Plan mutation
