# 04 — D4 I8 ENFORCEMENT (P0-F4 DECISION, 2026-09-05)

> D4 = APPROVED: I8 是 Production Core 硬约束

---

## 1. 冻结决策

**I8 = Production Core 硬约束**: Production artifact MUST NOT bypass canonical
Artifact lifecycle (S2 art-*)。

现状违反 (P0, F4 audit 证实): 真实外部执行产物 (exec ART-* 225 / EXS patch 75 /
org registry 24) 全部绕过 S2 lifecycle — art-* 真实 0 条。

**"生成文件以后再补 Artifact record" 不算满足 I8。** Artifact creation 必须属于
正式 production execution contract。

## 2. Canonical production path (冻结)

```
Task (TASK-*)
  → TaskRun (run-*)
  → External Execution
  → EXS-*
  → Artifact Creation (create_artifact — GENERATED, 强制)
  → Artifact Lifecycle (S2 8 态)
  → Verification (ver-*)
  → Evidence (EVD-*)
  → Audit (observation)
```

## 3. Contract 元素 (本阶段只定义, 不实现)

| 元素 | Contract |
|---|---|
| Artifact creation boundary | production execution 成功产出可持久化成果 (patch/文件/报告/test 证据) 时, **在执行完成回调内** create_artifact (同 execute_node_run/finalize 上下文) |
| Artifact writer | artifact_lifecycle.create_artifact (唯一; 经 node_runtime execute/finalize 适配) |
| Artifact repository | S2 前缀分片 store (唯一) |
| Lifecycle transition | S2 8 态 + fail_artifact; APPROVAL_GATES 经既有 approve |
| Failure semantics | create 失败 → run FAILED (现有 node_runtime 模式); transition 失败 → 抛错不伪装 |
| Idempotency | 同 attempt 同 exs 重复 create → 返回已有 (F4 impl: content-hash 或调用方去重) |

## 4. 旁路禁止 (F4 impl 强制)

- gateway/agent_runtime 产物不得只写文件/ART-* — 必须经 create_artifact 进入
  canonical (F4 impl 在 execution 完成路径接入)
- exec ART-* 保持 legacy 只读 (不删不改), 但新生产执行不再产生新 ART-*
  (除非显式 legacy 路径)
- 禁止绕过 S2 直接写 art 文件

## 5. 边界 (本阶段不实现)

I8 enforcement 的代码接入 (execute_node_run/finalize/gateway 适配 + exs_id 参数)
属 F4 implementation phase。
