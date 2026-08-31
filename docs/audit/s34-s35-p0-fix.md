# S34/S35 — Production Convergence P0 Fix 完成报告

> 日期: 2026-09-01 | 真实黑盒 E2E 证据

## 1. 6 个 P0 修复

```
P0-1 Phantom Plan:  production_claim_prompt — LLM 声称"计划已生成"必须有 plan_id 证据
                    (无 plan_id → 必须调 plan_development 或如实说未生成)
P0-2 False Execution: chain_start 生成 run_id + 写 exec_state + 关联 session.run_ids
                    (Run 真实可查: run_id + session 关联)
P0-3 Task 重复:     execute_plan 幂等 — 同 plan_id 已执行 → 返回已有任务不重复创建
P0-4 Task 无 plan_id: Task.plan_id 字段 + create_task 落库 (Plan→Task 链真实)
P0-5 project_tasks 空: Context→Tool 自动注入 — AI 识别项目后工具自动补 project_id
                    + 空参查询失败自动重跑修正
P0-6 Response Truth: production_claim_prompt 注入最终回答前 (工具结果 = 事实来源)
```

## 2. 黑盒 E2E 证据

```
用户: "给飞机大战项目出开发计划"
→ project_list + plan_development (真实) → plan_9f475cf2d526 + 8 任务计划 ✅

用户: "批准执行"
→ execute_plan True → 8 任务创建 (TASK-f646c338 等) ✅

用户: "再执行一次这个计划"
→ "8 个任务已确认存在于 backlog" (幂等! 任务总数 20 未增) ✅
```

## 3. 四方一致性(实测)

```
API /api/projects/P-b0adfaa6/progress: 20 任务
磁盘 backlog/task.json:                  20 任务
plan API:                                4 plans (latest plan_9f475cf2d526)
project_tasks 工具 (带 project_id):      20 任务
→ 完全一致 ✅
```

## 4. Plan→Task 链(真实落库)

```
TASK-16245fc9 | 实现玩家射击功能 | plan_id: plan_9f475cf2d526
TASK-1f141a93 | 实现敌机生成与移动 | plan_id: plan_9f475cf2d526
... 8 个任务全部带 plan_id ✅
```

## 5. 验证

```
✅ 后端: 1154 passed + 6 skipped
✅ 专项: 33/33 (+2 幂等/plan_id)
✅ 前端: 518/519 (af-todo-tree DEFERRED)
✅ tsc | build: PASS
✅ git clean (commit 37e99f80)
```

## 6. 架构改进

```
One Execution Path:
  Conversation → Tools → ConsoleService → Production Store
  (create_project/plan_development/execute_plan/chain_start/project_tasks
   全部走 Core, Context→Tool 自动注入 project_id)

Response Truth:
  LLM 是解释器, 不是事实来源
  声称生产对象必须有工具返回的 ID 证据
```

## 7. 剩余 P1

```
- chain_start 的 exec_state 与 workflow_runs 两套 Run 体系统一
- Phantom Plan 历史数据清理 (plan_b8eceef439ee 关联审批)
- 12 个历史重复任务清理
```
