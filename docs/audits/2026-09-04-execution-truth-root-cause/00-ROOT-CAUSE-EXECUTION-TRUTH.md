# 00 — ROOT CAUSE: EXECUTION TRUTH (P0 Forensic Audit)

> 日期: 2026-09-04 | READ ONLY | 仓库 /Users/Shared/work/ai-software-factory
> HEAD 1e993dec (main) | pyproject 1.1.364 | 数据根 ~/.factory
> 方法: 代码调用链追踪 (agent_loop/exec_state/gateway/task_registry/service/orchestrator/conversation_os)
> + 真实 ID 级数据取证 (session_exec 6 / external_tasks 9 / EXR 86 / EXS 100 / audit 5172 / backlog 235)
> + 版本时间线 (git log exec_state/agent_loop/gateway) + 测试实跑 (org+exec 2183, 主链 70)

---

## Executive Verdict (10 行内)

当前 Execution Truth Closure 为什么失败?

```
Primary Root Cause:
E — Dual (实际上 Multi) Task/Execution Model + 无跨账本 Canonical ID Contract。
系统并存 ≥6 套互不共享 ID 语义的 Task/Execution ledger; session_exec 只是其中一层,
且 6 个现存 session_exec 全部来自 E2E 验收测试 (project_id=None), 从未接真实项目上下文。

Secondary Causes:
C — exec_ref 被三个模块当成三种东西 (chain 写 TASK-GW-*; T-9 溯源按 EXR-* 读; Task model 注释=EXR/引擎 id)。
B — session_exec 状态机无自动收敛; 无 run 完成事件驱动; 依赖人工 chain_next/auto worker 推进;
     E2E 只推进 0-5 步就停止 → 6/6 running。
D — gateway project_dir 依赖 project_id→locate_repo; E2E 调用 project_id 空 → project_dir 空 → verify 诚实 unknown。

FX-01: SPLIT (不能直接实施 — 身份契约未冻结)

Canonical Task:     org.management.Task (backlog TASK-*) — 唯一有 model+SSOT+API+审计创建事件的层
Canonical Execution: 不存在 (EXR 请求 / EXS 结果 / TASK-GW 委派 / execution_records 四分)
Canonical Verification: 不存在 (verification.py 执行器真实, 但归属与存储未冻结; gateway verify 依赖 project_dir)
Canonical Audit:    audit_events.json (T0 层最接近 canonical, 但事件链未连接 backlog 执行生命周期)

最小正确修复边界:
冻结 身份契约 (Task/Execution/Verification 每域唯一 SSOT + ID 方向) → 再实施 FX-01 回写。
```

---

## 1. 背景与任务

上轮 Current State Baseline (2026-09-04-current-state-baseline.md) 记录异常:
exec_ref=None / session_exec 6/6 running / done tasks 无 exec_ref / verify=unknown /
audit TASK_STARTED·TASK_COMPLETED 疑似不属于当前 TASK-* backlog。

本审计目标: 判定这是**局部 writeback bug** 还是 **多 Task/Execution ledger 无统一契约的架构冲突**。

结论先行: **架构冲突 (E) + 契约缺失 (C) 为主; callback 缺陷是表象, 且 6 个 session_exec 均为
E2E 测试痕迹, 不是真实生产主链故障**。FX-01 直接实施 = 给未冻结的身份契约打补丁, 危险。

---

## 2. 顶层发现一览 (证据在 01/02/03/04 文件)

| # | 发现 | 证据 |
|---|---|---|
| F-1 | session_exec 是 **session 级编排状态**, 非 TaskRun/非 Execution | exec_state.py:1-96 (plan/tasks/status/current_index) |
| F-2 | 现存 6 个 session_exec 全部是 E2E 测试会话, project_id=None | session titles P0FIX-E2E/CORE-E2E/ORCH-E2E/PLAN-E2E (console_sessions.json) |
| F-3 | 6/6 running = E2E 只推进 0-5 步即停止; 无自动收敛 | 8/28-9/1 版 exec_state 无收敛定时器; idx 0/4/-1 分布 |
| F-4 | done task 无 exec_ref 字段 (非 None) | 8/28 版 exec_state.next() 根本不写 exec_ref (P2-② 是 9/2 才加) |
| F-5 | 委派真实完成: TASK-GW-* 6 done 各有 EXS-* result_id | external_tasks.json (9 条: 6 done/3 running, 6 有 result_id) |
| F-6 | verify=unknown 是 **诚实降级**: project_dir 空 → auto_verify 返回 unknown | executor.py:337-346 (无目录→unknown "无项目目录") |
| F-7 | project_dir 丢失根因 = project_id 空 → locate_repo 空 | gateway.py:133-148; E2E 调用 project_id="" |
| F-8 | audit TASK_STARTED/COMPLETED = M3 orchestrator (CLI 旧体系) 产物 | orchestrator.py:3223 (TASK_STARTED), 2174/2869 (TASK_COMPLETED); task_id=task-e1-core |
| F-9 | 当前 backlog TASK-* 从未有 audit STARTED/COMPLETED | ID 级验证: 235 TASK-* 中仅 52 条 TASK_CREATED, 0 条 STARTED/COMPLETED |
| F-10 | exec_ref 语义三义 | chain_next 写 TASK-GW (agent_loop.py:1581); T-9 溯源读 EXR (fastapi_adapter.py:913-918); Task model 注释=EXR/引擎 id (management.py:148-166) |
| F-11 | ≥6 套 Task/Execution ledger | 见 02-ID-LEDGER-MAP.md |
| F-12 | EXR 86 条 task_id = T001/T002/T003 (exec 内部) + task-e1-core (M3) — 非 backlog | requests.json 取证 |
| F-13 | org 27 项目 git_enabled=0, repo_path 仅 11 非空 — 项目工作目录契约未生效 | org/projects.json |
| F-14 | 生产 Web 路径 (run_agent_native→chain) 与 CLI 路径 (session.py→orchestrator) 并存 | fastapi_adapter 7040 vs cli_factory 8133 |

---

## 3. Actual Call Graph (Web 生产主链 8011)

```
POST /api/sessions/{id}/messages (fastapi_adapter.py:6980, stream SSE)
  └─ run_agent_native()  agent_loop.py:1779
       └─ LLM 循环 → 工具调用 dispatch()  agent_loop.py:2198
            ├─ chain_start   agent_loop.py:1409
            │    ├─ service.create_task() × N → backlog TASK-* (backlog_id 映射)  1419-1440
            │    ├─ ExecState.start()  → session_exec/<sid>.json status=running    1474-1477
            │    ├─ state.run_id/project_id/plan_id/session_id 写入                 1481-1497
            │    └─ [auto=true] _chain_auto_worker 线程                            1510-1523
            └─ chain_next   agent_loop.py:1530
                 ├─ ExecState.load → recover()   (9/2+ 版本)                       1539-1565
                 ├─ _exec_fn: gateway_execute(title, project_id=??? )              1567-1581
                 │    ├─ _pick_executor  gateway.py:117
                 │    ├─ ExternalTaskRegistry.create → TASK-GW-*  external_tasks.json 126-129
                 │    ├─ project_dir = locate_repo(data_dir, project_id)           133-148  ← project_id 空→目录空
                 │    ├─ executor.run(adapter, prompt, project_dir) → claude/codex 166
                 │    ├─ record_invocation → EXS-* + execution_records.json        176-184
                 │    ├─ _verify_output(project_dir) → auto_verify                186 → unknown (无目录)
                 │    └─ 返回 {task_id=TASK-GW, result_id=EXS, verify}             201-205
                 ├─ st.next(_exec_fn) → 写 task.status/result/verify (8/28 版无 exec_ref; 9/2+ 写) 1583
                 ├─ finish_task_exec(backlog)  (仅当 backlog_id 非空)               1595-1617
                 └─ reconcile_plan()                                               1619-1624
```

**断点标注**:
1. `chain_start` 建 backlog 需 project_id (会话绑定); 6 个 E2E 会话 project_id=None → create_task 失败/空 → backlog_id="" (session_exec 数据证实) → 后续回写全部跳过。
2. `chain_next` 的 `gateway_execute(project_id=project_id)` — project_id 来自 dispatch 闭包 (会话级), **不是 st.state["project_id"]** (agent_loop.py:1572 vs 1486: chain_start 把 project_id 存进了 st.state, chain_next 却没用它!) → 即使 st.state 有 project_id, gateway 也收不到。→ **上下文传播断点 (D)**。
3. 8/28 版 `exec_state.next()` 无 exec_ref 写回 (9/2 d6f1de6b 才加) → 8/31 的 done 任务无 exec_ref 是**版本时序**, 不是 callback bug。
4. 9/2+ 版本 exec_ref = `r.get("task_id")` = **TASK-GW-*** → 与 T-9 溯源期望 (EXR-*) 矛盾 → **exec_ref 语义三义 (C)**。
5. session_exec 完成需人工/auto 推进至全部 done → E2E 只推 0-5 步 → running 滞留 (B)。

## 4. Actual State Graph

```
Backlog Task (org.management)
  todo ──start_task_exec──> in_progress ──finish_task_exec──> done/failed/blocked/cancelled
    (service.py:4380-4566; 该路径在 agent_loop 619/1605、cli_factory 2595/2630 被调)
    ↑ 但 session_exec 链只有 backlog_id 非空才会调 finish_task_exec (agent_loop.py:1598)

session_exec (ExecState)
  idle ──start()──> running ──next()×N──> done   (exec_state.py)
    ↑ 无超时/无 run 事件驱动; auto worker 是唯一自动推进 (daemon thread)
    ↑ E2E: start 后 next() 0-5 次即停 → running 滞留

TASK-GW (ExternalTaskRegistry)          status: running → done|failed   (gateway.py:195-197)
EXR request (exec/requests.json)        (employee/AgentRuntime 域)
EXS result (execution_records.json)     record_invocation → 100 条       (executor.py:194-230)
M3 orchestrator task                    pending → running → completed/failed (orchestrator.py)
    ↑ 唯一发 TASK_STARTED/TASK_COMPLETED audit 的层 (旧 CLI 执行体系)
```

## 5. Actual Identity Graph (真实存在 / 缺失 FK)

```
session_id (sess-*, console_sessions)  REAL
  └→ plan_id (PLAN-*/plan_*, session_plans.json)  REAL; session_exec 内嵌但非 FK 引用
       └→ requirement_id (req_*, 4/16 plans)  PARTIAL
       └→ backlog task TASK-* (workspace)  REAL via plan_id (53 tasks)
            └→ exec_ref → ???  ❌ 三义 (TASK-GW vs EXR vs 引擎id)
                 └→ execution_id:
                      EXR-* (requests.json 86)  REAL (employee 域)
                      EXS-* (execution_records 100)  REAL (gateway/record_invocation)
                      TASK-GW-* (external_tasks 9)  REAL (委派控制面)
                      run_id R* (session_exec/console run_ids)  REAL (会话 Run 卡)
                 → 四者互不关联, 且都不被 backlog TASK-* 稳定引用
                      └→ artifact_id: ART-* (exec/artifacts.json 225) ↔ EXS-* (event_refs 数字序列, 非 id) 
                      └→ verification: 无独立 id/存储 (verify dict 内嵌)
                      └→ evidence: ev-*.json (ai-factory-self 9) 仅旧 production_run 域
                      └→ audit_event_id: audit_events.json REAL (但 STARTED/COMPLETED 只连 M3 legacy)
```

缺失 FK 链: `backlog TASK-* → EXR/EXS` (exec_ref 空/三义), `session_exec task → EXS` (exec_ref 空),
`TASK-GW → backlog TASK-*` (无映射), `audit STARTED → current TASK-*` (0 条)。

## 6. 最终 12 问速答

| # | 问题 | 答案 |
|---|---|---|
| P0-01 | 为何 exec_ref=None? | 6 个 session_exec 由 8/28-9/1 版代码产生, 该版 next() 不写 exec_ref (9/2 才加); 且 backlog_id 空 → 回写路径整体跳过 |
| P0-02 | 为何 6/6 running? | E2E 测试只推进 0-5 步即停止; 状态机无自动收敛/超时; auto worker 是 daemon 依赖进程存活 |
| P0-03 | 外部执行完成否? | 是 — TASK-GW 6 done 各有 EXS-* (claude/codex 真实委派); EXS report 含 usage/验证 |
| P0-04 | Execution completion canonical producer? | 不存在单 producer: gateway (EXS/TASK-GW), AgentRuntime (EXR/EXS), orchestrator (M3) 三路 |
| P0-05 | Task completion canonical producer? | 双 producer: service.finish_task_exec (backlog) vs ExecState.next (session_exec) — 未统一 |
| P0-06 | Verification canonical producer/storage? | verification.py 执行器真实 (pytest/syntax); 无独立 SSOT/存储; gateway verify 内嵌 dict, 依赖 project_dir |
| P0-07 | Artifact 属当前 Task? | 否 — exec ART-* 挂在 EXS-* 下 (event_refs 数字序列), 不经 backlog TASK-*; org artifacts 24 条另属 org 工作流 |
| P0-08 | project_dir 丢在哪? | chain_next 调 gateway 用 dispatch 闭包 project_id (agent_loop.py:1572), 弃用 st.state["project_id"] (1486) — caller 传错源; E2E 时两者皆空 |
| P0-09 | TASK-* 与 task-e1-core 同 model? | 否 — TASK-* = org.management.Task (backlog SSOT); task-e1-* = orchestrator M3 内部任务 (旧 CLI 执行) |
| P0-10 | 几个 ledger? | ≥6: backlog/session_exec/TASK-GW/EXR/EXS/M3 orchestrator (+factory.db 事件镜像, audit) |
| P0-11 | 哪个应 canonical? | Task=backlog TASK-* (唯一有 model+SSOT+API+audit 创建); Execution/Verification 需新冻结 (现状无) |
| P0-12 | FX-01 可直接实施? | **NO — SPLIT** (身份契约未冻结; 见 05-FX01-BOUNDARY.md) |

---

## 7. 结论

这不是一个 "callback 没接好" 的局部 bug, 而是:

**AI Factory 在执行域存在多代并行账本 (M3 orchestrator 旧 CLI / chain session_exec / gateway TASK-GW /
exec EXR-EXS / org backlog), 各账本 ID 语义独立, 无统一 ownership 与 canonical truth contract。
当前主链 Web 会话路径 (run_agent_native→chain→gateway) 的代码已具备委派→EXS 真实记录能力,
但 backlog 回写依赖 (a) 会话 project_id 绑定 (b) backlog_id 映射 (c) 9/2+ 的 exec_ref 写回,
三层在 8/28-9/1 的 E2E 运行中全部缺位 → 数据表现为 exec_ref=None + running 滞留 + verify unknown。**

真正需要修的 contract: ① 每域唯一 SSOT+ID 方向冻结 (Task→Run→Record→Artifact→Verify→Evidence)
② exec_ref 单一语义 ③ chain_next 上下文传播 (st.state.project_id) ④ session_exec 收敛驱动
⑤ legacy audit/数据标记 historical (不硬接)。

---
---

==================================================
P0 ROOT CAUSE STATEMENT
==================================================

Primary Root Cause:
E — Multi-Task / Multi-Execution Ledger Architectural Conflict (≥6 套互不共享 ID 语义的
Task/Execution 账本: backlog TASK-* / session_exec / TASK-GW-* / EXR-* / EXS-* / M3 orchestrator
task-e1-*), 且无跨账本 Canonical Identity Contract。当前主链 (Web chain) 的委派与记录能力
真实 (EXS 100 条含 claude/codex 委派), 但 backlog 回写、验证归属、审计生命周期全部落在
不同账本上, 互相不可见。

Secondary Causes:
C — exec_ref 语义三义 (chain 写 TASK-GW / T-9 溯源读 EXR / model 注释=EXR-引擎 id);
    EXR→EXS 链接 0/86。
D — chain_next 上下文传播断: gateway 用 dispatch 闭包 project_id, 弃 st.state["project_id"];
    E2E 运行时 project_id 空 → project_dir 空 → verify 诚实 unknown。
B — session_exec 状态机无自动收敛/超时; E2E 只推进 0-5 步即停 → 6/6 running 滞留。

Evidence:
- external_tasks.json 9 条 (6 done 各有 EXS-* result_id; verify 9/9 unknown; project_id 8/9 空)
- session_exec 6 文件: 2 代代码代际 (8/31 无 run/proj/plan; 9/1 有), 全部 E2E 测试会话 (project_id=None),
  done 任务无 exec_ref 字段 (8/28 版代码不写; 9/2 d6f1de6b 才加)
- audit: 当前 TASK-* 235 条仅 52 TASK_CREATED, 0 STARTED/COMPLETED; legacy task-e1-* 有完整生命周期 (8/18)
- agent_loop.py:1572 (gateway 用闭包 project_id) vs 1486 (st.state.project_id 已存未用)
- fastapi_adapter.py:913-918 (T-9 按 EXR 溯源) vs agent_loop.py:1581 (exec_ref=TASK-GW)
- orchestrator.py:3223/2174/2869 (M3 audit producer, project_dir.name 数字 id)

Canonical Truth:
- Task = backlog TASK-* (org.management.Task, 唯一 model+SSOT+API+创建审计)
- Execution = 不存在单 canonical (EXR/EXS/TASK-GW/run_id 四分) — 需冻结 (建议 EXS)
- Verification = 不存在 canonical (FX-08 未做) — verify dict 内嵌
- Audit = audit_events.json 最接近事件 canonical, 但执行生命周期只连 legacy

Broken Contract:
- Task→Execution Ownership (exec_ref 空/三义; backlog 0/235 有引用)
- Execution→Result Link (EXR.output_refs 0/86)
- Execution→Artifact→Verification FK 方向 (ART 挂 EXS 数字 event_refs, 不经 Task)
- Audit↔Backlog 生命周期 (STARTED/COMPLETED 不覆盖当前 TASK-*)
- Gateway 上下文 (project_id 传播到 project_dir)

FX-01:
SPLIT — 先身份契约冻结 (F0), 再 EXS 规范化 (F1), 后回写闭环 (F2); 不可直接实施

Minimal Correct Fix Boundary:
见 05-FX01-BOUNDARY.md §2 (MUST CHANGE) / §3 (MUST NOT CHANGE)

Must Fix Before FX-01:
1. Identity Contract (零代码冻结: 每域唯一 SSOT + ID 方向 + exec_ref=EXS 唯一语义 + legacy 标记)
2. chain_next 上下文修复 (st.state.project_id 传播到 gateway)
3. 决定 session_exec 去留 (Run 投影 or 废弃) + E2E 遗留处置

Must NOT Touch:
- legacy audit 记录 (8/18 task-e1-*) / historical EXR·EXS·results.json / 现有 Artifact 生命周期
- WebUI / orchestrator M3 代码 / factory.db·audit_events 历史事件
- 不得为"统一"强行重连历史数据

==================================================
END
==================================================
