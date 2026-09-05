# 01 — ARTIFACT SSOT (P0-F4 ACCEPTANCE, 2026-09-05)

> A1-A3 验收证据

---

## 1. A1: canonical writer = 1

```
create_artifact 调用者 (全仓):
  factory-console/node_runtime.py:275   — _absorb_execution_artifact (F4 I8 收纳)
  factory-console/node_runtime.py:538   — execute_node_run (workflow 域)
  factory-console/rollback_service.py:274 — 恢复域 (rollback 新产物)
```

直接写 art 文件路径 (_write_artifact/_artifact_path/_artifacts_dir):
仅 artifact_lifecycle.py 内部 (grep 确认零外部)。

**canonical Artifact writer = artifact_lifecycle.create_artifact (单一入口, 锁内)**
competing stores = 0 (S2 前缀分片唯一 store)。

## 2. A2: 无旁路创建 canonical art-*

| 潜在旁路 | 结果 |
|---|---|
| exec ART-* | 不产 art-* (exec 域独立, F4 前 legacy) |
| org ArtifactRegistry | 不产 art-* (org 域) |
| EXS patch file | 不产 art-* (文件名非 FK) |
| audit event | 不产 (audit observation) |
| WebUI | 零 create_artifact (只读 GET) |
| CLI | 零 create_artifact (artifact list/get 只读) |
| manual registration API | 无 (全仓搜零命中) |

## 3. A3: EXS → canonical art-* (真实路径)

```
finalize_node_run (agent_loop 委派完成回调, 2 处)
  → _absorb_execution_artifact (node_runtime:441)
  → create_artifact (artifact_lifecycle, exs_id=EXS-*)
  → art-* (GENERATED)  ← canonical
```

gateway.py / external executor.py 对 ART-* 写入 = 0 (grep 计数 0) — legacy 旁路
未扩展, 新生产执行只进 canonical art-*。

## 4. 结论

**A1 PASS | A2 PASS | A3 PASS** — art-* 是唯一 canonical Artifact。
