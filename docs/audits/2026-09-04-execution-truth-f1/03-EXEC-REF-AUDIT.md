# 03 — EXEC-REF AUDIT (P0-F1, 2026-09-04)

> exec_ref 全量语义审计 — F1 后仍存歧义点 / 已修正点 / legacy 保留点

---

## 1. exec_ref 写点 (F1 后)

| 位置 | 写入值 | F0 语义 | 状态 |
|---|---|---|---|
| agent_loop.py chain_next _exec_fn | `r.result_id or r.task_id` → EXS-* | ✅ EXS | 修正 |
| agent_loop.py auto worker _exec_fn | `r.result_id or r.task_id` → EXS-* | ✅ EXS | 修正 |
| agent_loop.py finish_task_exec 回写 | `_cur.exec_ref or _bid` → 副本已存 EXS | ✅ EXS | 修正 (原取 _v.exec_ref=空) |
| service.start_task_exec | 透传调用方参数 | 中性 (由调用方给) | 保持 |
| service.finish_task_exec | 透传调用方参数 | 中性 | 保持 |
| cli_factory.py:2598 bridge | `f"bridge:{tid}"` | legacy (自有格式) | **保留 (legacy adapter)** |
| cli_factory.py:2624 bridge | `result.request_id` (EXR-*) | legacy | **保留 (legacy adapter)** |
| exec_checkpoint | 镜像 exec_ref | 中性 | 保持 |
| exec_state.py (session_exec 副本) | 透传 _exec_fn 返回值 | ✅ 现为 EXS | 修正 (经 _exec_fn) |

## 2. exec_ref 读点 (F1 后)

| 位置 | 读取逻辑 | F0 语义 | 状态 |
|---|---|---|---|
| fastapi_adapter _task_exec_trace | **先按 EXS 直查 execution_records; 命中返回; 未命中 → EXR legacy 回退** | ✅ EXS canonical | 修正 |
| fastapi_adapter 1061/7596 (展示) | 文本显示 exec_ref | 中性 | 保持 |
| exec_state.recover | run_status_fn(exec_ref) → registry 查询 | 依赖运行 registry | 见 §3 |
| cli_factory 2576/2587 (中断恢复) | 读 task.exec_ref | 中性 | 保持 |

## 3. 遗留歧义 (诚实声明)

1. **exec_state.recover**: 用 exec_ref 查 ExternalTaskRegistry (TASK-GW 状态)。F1 后 exec_ref=EXS,
   registry 查 EXS 会 miss → UNKNOWN → 重排队 (安全降级, 不伪造)。TaskRun (NodeRun) 状态驱动
   的恢复属 F2 — 本 Sprint 不改 recover 语义 (避免提前实现 convergence)。
2. **CLI bridge (cli_factory 2598/2624)**: 写 bridge:/EXR 格式。已由 T-9 EXR legacy 回退兼容;
   保留为 legacy adapter (CLI 外部执行路径, 非 Web 主链)。标记: 不迁移, 后续若 CLI 统一走
   chain/gateway 则自然消除。
3. **旧历史 backlog task exec_ref (exec_result 文本/EXR)**: 不清除不迁移 (F0 硬约束)。

## 4. 生产代码 exec_ref canonical interpretation 冲突

F1 后生产代码 (Web 主链 + T-9) 无与 F0 冲突的 exec_ref interpretation。
唯一非 EXS 写点 = CLI bridge (legacy adapter, 已标记); 唯一非 EXS 读依赖 = recover (F2)。
