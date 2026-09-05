# 01 — CALL GRAPH (P0-F4 IMPL, 2026-09-05)

> F4 后真实调用链

---

## 1. Chain 生产路径 (I8 已接入)

```
agent_loop._exec_fn (chain_next / auto worker)
  → gateway_execute (真实外部 CLI) → record_invocation → EXS-*
  → finalize_node_run(success, exs_id=_exs, output, artifact_root=root)
      → _absorb_execution_artifact (create_artifact type=report, exs_id 幂等) → art-*
      → _materialize_verify (artifact_ids=[art]) → ver-*
      → _attach_verify_evidence (真实 verifier 输出) → EVD-*
  → NodeRun COMPLETED
  → finish_task_exec → Task done
```

## 2. Workflow 路径 (execute_node_run)

```
execute_node_run (executor_fn)
  → create_artifact (每 attempt 新, I10) → art-* (node_run_id)
  → _materialize_verify (artifact_ids=[art]) → ver-*
  → _attach_verify_evidence (verification dict 真实内容) → EVD-*
  → NodeRun COMPLETED / FAILED→repair
```

## 3. 查询路径

```
CLI:  factory artifact list|get → artifact_lifecycle (S2 canonical)
       factory evd list|get     → evidence_domain (EVD-*)
       factory verification list|get → verification_domain (F3)
API:  (F3 T-9 投影 verifications; F4 未新增 API — 任务书最小暴露)
```

## 4. Writer 清单 (唯一)

| 对象 | 唯一 writer |
|---|---|
| art-* | artifact_lifecycle.create_artifact |
| ver-* | verification_domain.materialize_verification (F3) |
| EVD-* | evidence_domain.materialize_evidence |
| EXS | record_invocation (F1) |
| run-* | node_runtime (F1) |
