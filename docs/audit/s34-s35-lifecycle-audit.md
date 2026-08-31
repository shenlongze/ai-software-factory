# S34/S35 — Conversation → Production Core 全生命周期一致性审计

> 日期: 2026-09-01 | 纯审计 (不修复) | 真实存储 + API + 会话证据

## 1. 飞机大战生命周期真实数据

### Project
```
org: P-b0adfaa6 飞机大战 | lifecycle: idea | 唯一项目 ✅
目录: projects/P-b0adfaa6/ 存在 ✅ | workspace/projects/P-b0adfaa6/ 存在 ✅
Git: 未初始化 (诚实 not_initialized) ✅
Project Identity: 全入口一致 ✅
```

### Requirement
```
requirements.json: req_0862000369e0 (project_id=P-b0adfaa6) ✅
存在但 API 无独立查询端点 (详情返回) ⚠️
```

### Plan — BROKEN (Phantom Plan)
```
session_plans.json 真实 Plans:
  plan_d92f9c23070a (sess-c7ec7c5aa, P-b0adfaa6, appr-ca3288682a)
  plan_01262486eed4 (sess-650209fdf, P-b0adfaa6, appr-c8f0751e13)
  plan_c35c6c3a1b2b (sess-05235fcf0, P-b0adfaa6, appr-6d19bc318e)
⚠️ plan_b8eceef439ee: 审批 appr-fafed0f69e 存在 (subject_ref=plan_b8eceef439ee),
   但 session_plans.json 无此 Plan 实体!
   → Phantom Plan: LLM 回答声称"重新生成计划 plan_b8eceef439ee"但未真实落盘
   → 根因: AI 直接在回答里"重新生成"而未调 plan_development 工具
```

### Approval — PARTIAL
```
7 条审批全部真实存在 ✅
appr-6d19bc318e = APPROVED (plan_c35c6c3a1b2b) ✅
appr-fafed0f69e = PENDING (phantom plan) ⚠️
✅ 批准绑定 plan_id (subject_ref)
```

### Task — BROKEN (重复 + 无 plan 关联)
```
backlog/task.json: 12 任务 (全部 P0, status=todo) — 真实存在 ✅
6 个声称的 TASK ID 全部真实存在 ✅ (TASK-ca553ba9 等)
❌ 12 任务含重复: 初始化骨架×2 / 游戏主循环×2 / 子弹×2 / 敌机×2 / 碰撞×2 / 玩家绘制×2
   (execute_plan 被调用 2 次, 每次建 6 个)
❌ 全部 task.plan_id = None (无 Plan→Task 关联)
```

### Run — MISSING (False Execution Success)
```
❌ workflow_runs/P-b0adfaa6/ 不存在 — Run 从未启动
❌ exec_state: running, 5 任务, backlog_id 空 (chain_start 建的但未关联 backlog)
❌ Conversation 声称"开始执行"但无真实 Run → False Execution Success
```

## 2. 核心矛盾根因

```
用户"我要看任务执行进度" → project_tasks 返回"暂无/0%"
根因: project_tasks 工具收到 project_id 为空 (company 会话)
  → 手动带 P-b0adfaa6 调 project_tasks → 真实返回 12 任务!
  → 与 execute_plan/chain_start 同一模式: 工具缺 project_id 传递
```

## 3. P0 Findings

```
P0-1: Phantom Plan (plan_b8eceef439ee) — LLM 声称创建但无实体
      → 根因: AI 未调 plan_development 工具就声称"计划已生成"
P0-2: False Execution Success — Conversation 说"开始执行"但无 Run
      → chain_start 建 exec_state 但未启动真实 workflow Run
P0-3: Task 重复创建 (12 = 2×6) — execute_plan 多次执行无幂等
P0-4: Task 无 plan_id 关联 (12 任务 plan_id 全 None)
P0-5: project_tasks 工具 project_id 空 → 查询"暂无" (工具缺参传递)
P0-6: Conversation Response Truth 违约
      "6 个 P0 任务已全部创建" ✅ 真实 (但重复)
      "开始执行" ❌ 无 Run
      "开发计划已批准" ⚠️ 部分 (approved 是另一个 plan)
```

## 4. Production Chain 评级

```
Session       REAL (console_sessions 一致)
→ Requirement REAL (requirements.json)
→ Project     REAL (org SSOT 一致)
→ Plan        BROKEN (phantom plan_b8eceef439ee)
→ Approval    REAL (7 条真实, subject_ref 绑定)
→ Task        BROKEN (重复 + 无 plan_id)
→ Run         MISSING (从未启动)
→ Artifact    PARTIAL (exec_state 产物, 未关联)
→ Verification MISSING
→ Status      PARTIAL (API 12 任务但 project_tasks 空)
```

## 5. One Execution Path — BROKEN

```
✅ create_project → ConsoleService (统一)
✅ plan_development → session_plans (真实)
❌ AI 回答中"重新生成计划"绕过工具 (phantom)
❌ chain_start → exec_state (独立路径, 未启动 workflow_run)
❌ execute_plan 重复调用 (无幂等)
```

## 6. 最终评级

```
One Execution Path:  BROKEN
Data Truth:          BROKEN (phantom plan / 重复 task)
Cross Interface:     PARTIAL (API 12 任务 vs project_tasks 空)
Context Resolution:  PARTIAL (F1 已修, 工具缺 project_id 传递)
Monitoring:          BROKEN (project_tasks 空 vs API 12)
Cost:                PARTIAL (usage 真实, 无项目累计)
Cache:               REAL (无业务缓存)
Continuity:          PARTIAL (会话恢复, 链不完整)
最终: NOT READY (P0 未修)
```

## 7. 推荐 Fix 顺序

```
1. P0-6/5: project_tasks/chain_start/execute_plan 工具 project_id 统一传递
   (AI 识别项目后所有工具带 project_id — 已修 plan_development, 需扩展)
2. P0-1: Conversation Response Truth — AI 声称"计划已生成"必须有 plan_id
   (工具结果引用约束: 无 plan_id 不能说已生成)
3. P0-2: chain_start 启动真实 Run (workflow_runner) 或诚实"任务已建未执行"
4. P0-3: execute_plan 幂等 (按 plan_id 去重, 不重复建任务)
5. P0-4: task.plan_id 关联落库
```
