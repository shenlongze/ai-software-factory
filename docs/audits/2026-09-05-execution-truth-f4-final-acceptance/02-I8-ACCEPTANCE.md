# 02 — I8 ACCEPTANCE (P0-F4 ACCEPTANCE, 2026-09-05)

> D4/I8 验收证据

---

## 1. 代码路径证明

```
生产执行 (真实外部 CLI)
  → agent_loop._exec_fn (chain_next / auto worker)
  → gateway_execute → record_invocation → EXS-*
  → finalize_node_run (同一 completion pipeline)
      ├── _absorb_execution_artifact → create_artifact → art-*   ← I8 (P0)
      ├── _materialize_verify → ver-*
      └── _attach_verify_evidence → EVD-*
  → NodeRun COMPLETED → finish_task_exec → Task done
```

- _absorb_execution_artifact **唯一调用点 = finalize_node_run 内** (node_runtime:441)
- finalize_node_run **唯一调用者 = agent_loop 委派完成回调** (2 处: auto worker +
  chain_next) — 均在 execution completion pipeline 内
- 无独立 registration API (全仓搜 "register.*artifact / create_artifact_api /
  artifact post" = 零命中)

## 2. 不存在 post-hoc path

```
execution completed → pipeline ended → separate registration API → art-*
```
搜索零命中。Artifact creation 属于 production execution contract (D4 定义达成)。

## 3. Artifact lifecycle

- art-* 复用 S2 8 态 (GENERATED→…→RELEASED) + FAILURE_STATES + APPROVAL_GATES —
  未重定义 (E2E-1: art state=GENERATED, 合法起点)
- 每次 attempt 新 art (I10 不可变), fail_artifact 处理失败态

## 4. 结论

**I8 PASS** — Artifact creation 属执行 contract, 无 post-hoc 补登记。
