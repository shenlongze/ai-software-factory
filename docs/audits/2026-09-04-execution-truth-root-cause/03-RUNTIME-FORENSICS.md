# 03 — RUNTIME FORENSICS (Execution Truth Root Cause)

> 取证日期: 2026-09-04 | READ ONLY | ~/.factory 真实数据 ID 级重建

---

## 1. session_exec 6 文件逐一重建

数据源: ~/.factory/session_exec/*.json + console_sessions.json (会话标题/项目)

| session | 会话标题 | project_id | created | run_id/proj/plan/sess 字段 | backlog_id 存在? | idx | done/total | status | updated |
|---|---|---|---|---|---|---|---|---|---|
| sess-05235fcf06 | P0FIX-E2E | None | 08-31 17:09 | ❌ 全无 | 无 (0) | 0 | 1/5 | running | 08-31 |
| sess-134c852dbd | CORE-E2E | None | 08-31 16:46 | ❌ 全无 | 无 (0) | 4 | 5/12 | running | 08-31 |
| sess-0abb1e704d | PLAN-E2E-3 | None | 09-01 17:01 | ✅ 全有 | 有 | -1 | 0/6 | running | 09-01 |
| sess-9e334bbea2 | ORCH-E2E-3 | None | 09-01 17:21 | ✅ 全有 | 有 | -1 | 0/6 | running | 09-01 |
| sess-b5ac9b0bbd | ORCH-E2E-4 | None | 09-01 17:21 | ✅ 全有 | 有 | -1 | 0/1 | running | 09-01 |
| sess-f843d8fe69 | ORCH-E2E-2 | None | 09-01 17:19 | ✅ 全有 | 有 | -1 | 0/15 | running | 09-01 |

**两组代码代际**:
- 第一代 (8/31, 2 个): 8/28 v1.1.244 代码 — chain_start 不写 run_id/project_id/plan_id/session_id, create_task 用会话 project_id (None) → 失败 → backlog_id=""。chain_next 推进 1-5 步 (真实委派 claude/codex) → done 任务产生, 但 8/28 版 next() 不写 exec_ref → 数据无该字段。
- 第二代 (9/1, 4 个): 9/1 S34-P0-FIX 后代码 — 写全 run_id/project_id/plan_id/session_id + backlog_id。但 idx=-1 = chain_start 后**从未 chain_next** → 0 done, 全 todo。

**结论**: 6/6 running 不是"执行卡住", 是 E2E 验收运行只启动 (或推进 1-5 步) 后停止; session_exec 无自动收敛, 状态保留为 running。

## 2. 真实委派 → EXS 记录对应 (execution_records.json 12 条 success 委派)

| session_exec done 任务 | external_tasks TASK-GW | EXS result | agent | project_dir | verify |
|---|---|---|---|---|---|
| 项目骨架与页面结构搭建 | TASK-GW-47d2c100 | EXS-2f301554 | claude | (空) | unknown |
| 游戏循环与状态管理核心 | TASK-GW-56783738 | EXS-bb19cfda | claude | (空) | unknown |
| 玩家飞机控制模块 | TASK-GW-dd8dd927 | EXS-66eda2b3 | claude | (空) | unknown |
| 子弹系统（玩家与敌机） | TASK-GW-249647cc | EXS-4f2b9518 | claude | (空) | unknown |
| 敌机生成与移动系统 | TASK-GW-f3ad04b5 | EXS-08bc06aa | claude | (空) | unknown |
| 搭建项目基础结构 | TASK-GW-cf995d78 | EXS-e2bd72e1 | codex | (空) | unknown |
| (examiner 测试) | TASK-GW-* ×3 | EXS-8090c4fe 等 | claude.architecture-examiner | /tmp | unknown/pass×1 |

**证明**: 委派真实完成 (EXS 存在 + report.md usage/cost + 语法验证); 但 project_dir 全空 (E2E project_id 空 →
locate_repo 空) → auto_verify 诚实 unknown → gateway 层验证空转。**不是"没执行", 是"执行了但上下文与验证丢失"**。

## 3. audit 事件 ID 级抽样

**当前 backlog TASK-* (235 条) → audit**:
- TASK_CREATED: 52 条 (有创建事件, producer service.py:4035)
- TASK_STARTED / TASK_COMPLETED / TASK_FAILED: **0 条**
- 抽样 TASK-9d6b9101 / TASK-4f2c4c0f / TASK-e0c48bc7 / TASK-dfed1797 / TASK-cf59a92c → NO AUDIT EVENTS

**legacy task-e1-* → audit (8/18, M3 orchestrator)**:
- task-e3-manage: TASK_STARTED 1 / ARTIFACT_CREATED 1 / TASK_COMPLETED 1
- task-e1-manage: TASK_STARTED 2 / TASK_COMPLETED 1 / TASK_FAILED 1 / ARTIFACT_CREATED 2
- task-e2-core / task-e4-core / task-e4-view: STARTED 1-2 / COMPLETED 1 各

**project_id 证据**: legacy 事件 project_id=1787033426 (旧数字目录名), producer orchestrator.py:3223 用 project_dir.name。

**结论**: audit 的 STARTED/COMPLETED 完整生命周期只存在于 M3 orchestrator (CLI 旧体系) 的
task-e1-* 任务; 当前 backlog TASK-* 从未进入执行审计生命周期 → 两套 Task 系统, ID 不互通。

## 4. EXR/EXS/TASK-GW 账本核对

- execution_records.json: 100 条 (EXS-*, intent/action/agent/task/result/result_id/timestamp + 15 条扩展字段)
  - 85 条 action=agent.execute_task (8/14-8/18, backend-1×48/flutter-dev×17 等)
  - 15 条 action=external_ai.invoke (8/26-8/31, claude/codex 委派)
  - 87 success / 13 failed
- exec/results.json: 85 条 = execution_records 子集投影 (85/100 result_id 对上)
- exec/requests.json: 86 条 EXR-* (task_id=T001/T002/T003/task-client-ui/task-e1-* 等; output_refs=0/86)
- exec/external_tasks.json: 9 条 TASK-GW-* (6 done/3 running; 6 有 result_id=EXS; verify 9/9 unknown; project_id 8/9 空)

**结论**: EXR (请求) 与 EXS (结果) 是两个独立记录流, output_refs 从未链接;
TASK-GW 是第三个委派控制面, 与 backlog/session_exec 无映射。

## 5. Verification 取证

- verification.py: verify_python_syntax / verify_pytest 真实 subprocess; 无独立持久化 id
- executor.py auto_verify (337): 无 project_dir → unknown "无项目目录"; 有目录 → verify_hook 或 pytest
- EXS 记录 verify 字段 15/15 默认 unknown; test_result artifacts 75 条 (exec 域, 8/14-8/18)
- release_service._run_verification: 调 verify_pytest (代码存在, 无 releases 数据 → 未运行)

**结论**: Verification 有真实执行器但 **无 canonical SSOT / 无独立 id / 无跨链消费** (FX-08 未做);
gateway 委派 verify 因 project_dir 空而空转是"诚实降级"而非伪造。

## 6. 时间线 (版本 vs 数据)

| 日期 | 代码事件 | 数据痕迹 |
|---|---|---|
| 8/14-8/18 | exec 域 employee/backend 执行 (85 EXS, 87 success 记录) | execution_records 100 主体 + EXR 86 + audit TASK_*(M3, task-e1-*) 29/30/5 |
| 8/26-8/31 | gateway 委派 (claude/codex) 15 条 | external_tasks 9 + EXS external_ai 15 |
| 8/28 | v1.1.244: chain_start/next + backlog 打通 (P0-A) | 8/31 第一代 session_exec (CORE-E2E/P0FIX-E2E) |
| 9/1 | S34/S35-P0: run_id/project_id/plan_id 写入 + auto worker | 9/1 第二代 session_exec (PLAN/ORCH-E2E) |
| 9/2 | d6f1de6b: exec_ref 回写 + recover (P2-②) | (尚无新 session_exec 数据) |
| 9/4 | 本审计 | 6/6 running 遗留 (8/31-9/1 产物) |
