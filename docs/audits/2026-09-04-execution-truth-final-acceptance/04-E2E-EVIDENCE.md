# 04 — E2E EVIDENCE (P0-FINAL, 2026-09-04)

> 验收复跑证据 — 真实 external CLI (hermes), 隔离 tmp, 非 mock

---

## 1. 复跑结果 (2026-09-04, 验收时)

```
F1+F2 测试: 24/24 passed (tests/console/test_p0_f1_identity_relations.py 16
           + test_p0_f2_writeback.py 8)

E2E-1 SUCCESS (真实 hermes CLI):
  Task: TASK-a60181f2
  TaskRun: run-713d9b6903a2 (task_id=TASK-a60181f2)
  gateway ok: True | EXS persisted: task_id + task_run_id 锚
  TaskRun COMPLETED → Task done (exec_ref=EXS)
  → PASS

E2E-2 FAILURE (无执行器真实 gateway 分支):
  TaskRun FAILED → Task failed (无错误 COMPLETED) → PASS

E2E-3 IDEMPOTENCY (4× finalize 含失败尝试):
  COMPLETED 不变, history 无重复, EXS 记录=1 → PASS

E2E-4 RECOVERY (attempt1 FAILED → attempt2 hermes SUCCESS):
  最终 Task done, exec_ref=最终 EXS → PASS
```

## 2. 证据文件

- E2E 脚本: /tmp/f2_e2e.py (E2E-1), /tmp/f2_e2e_fail.py (E2E-2/3/4)
  (工作区外, 未提交; 每次新隔离 tmp 目录)
- 单元证据: tests/console/test_p0_f1_identity_relations.py (16),
  tests/console/test_p0_f2_writeback.py (8)

## 3. 无 Fake E2E 确认

- 未手工改 JSON / 未手工写 Task 状态 / 未直接调 writeback 绕过 production chain
- 未用历史 EXS / session_exec; 未从 audit 构造结果
- 外部执行 = 真实 hermes CLI subprocess (非 mock)
- 全链: build_console_service → create_project → create_task → _chain_task_run →
  gateway_execute (真实 CLI) → record_invocation (EXS) → finalize_node_run →
  finish_task_exec

## 4. 完整回归证据 (先前轮, 数据不变)

- org+exec 2183 passed; console/llm/s7 相关 398 passed; 累计 ~2605 effective
- test_agent_loop 11 failed = 预存 (stash 对照 before==after)
- test_concurrency / test_m3e_full_chain 偶发 = 多进程/高负载时序 (单独跑通过,
  不触 F2 文件; orchestrator 不 import node_runtime)
