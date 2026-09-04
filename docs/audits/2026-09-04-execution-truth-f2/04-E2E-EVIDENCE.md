# 04 — E2E EVIDENCE (P0-F2, 2026-09-04)

> 真实 E2E 证据 (F2 §14/§15) — 非 mock, 非手工改 JSON

---

## 1. E2E 方法

隔离 tmp 工作区 (不碰 ~/.factory); 真实生产代码路径:
build_console_service → create_project → create_task → _chain_task_run →
**gateway_execute → 真实 hermes CLI subprocess** → record_invocation (EXS) →
finalize_node_run → finish_task_exec。无 mock 执行器, 无手工状态写入。

## 2. E2E-1 SUCCESS (真实 hermes 委派)

```
workroot: /var/folders/.../f2-e2e-c596kdkb (隔离 tmp)
Task:         TASK-fb7f3653
TaskRun:      run-eb5884c5eb0b   (task_id=TASK-fb7f3653, 持久化)
gateway ok:   True  | EXS: EXS-712fff12  | verify: unknown (无项目目录诚实)
TaskRun state: COMPLETED
Task state:    done   | exec_ref: EXS-712fff12
EXS persisted: True   | task_id=TASK-fb7f3653 | task_run_id=run-eb5884c5eb0b
→ PASS
```

## 3. E2E-2 FAILURE (无执行器分支 — 真实 gateway 逻辑)

```
gateway ok: False | error: 无可用外部执行器 (设置→外部AI 配置)
TaskRun state: FAILED
Task state:    failed
→ PASS (无错误 COMPLETED)
```

## 4. E2E-3 IDEMPOTENCY

```
4 次 finalize (含 success=True ×3 + success=False ×1):
TaskRun state: COMPLETED (不被失败调用逆转)
history transitions: ['PENDING','RUNNING','VERIFYING','COMPLETED'] (无重复)
EXS records for run: 1 (无重复创建)
→ PASS
```

## 5. E2E-4 RECOVERY

```
attempt1 (无执行器): TaskRun FAILED → Task failed
failed → (start_task_exec 重试路径) → in_progress
attempt2 (真实 hermes): TaskRun COMPLETED → Task done | exec_ref=EXS-6ce5b710 (最终 EXS)
→ PASS (最终 Task 反映最终 canonical TaskRun outcome)
```

## 6. 执行命令 (可复跑)

```bash
timeout 280 .venv/bin/python /tmp/f2_e2e.py        # E2E-1
timeout 280 .venv/bin/python /tmp/f2_e2e_fail.py    # E2E-2/3/4
```
脚本在 /tmp (工作区外, 未提交); 每次运行新隔离 tmp 目录。
