# 07 — STATE OWNERSHIP (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> Artifact/Evidence owner 现状 (多 owner = 无 canonical)

---

## 1. Artifact owner 矩阵 (4 套)

| 账本 | Writer | State owner | Reader | 与 canonical 冲突 |
|---|---|---|---|---|
| S2 art-* | execute_node_run / rollback | artifact_lifecycle (唯一, I10 不可变) | governance/health/agent_kernel/workforce/release/recovery | run-* 有 FK 但 0 数据 |
| exec ART-* | AgentRuntime._write_artifact_file | exec store (无状态机) | exec 查询/T-9 | task_id 非 canonical |
| org registry | ArtifactRegistry | org domain (stage) | org API | P-* project 域 |
| EXS patch | record_invocation (外置) | 无 (文件系统) | T-9 | EXS 文件名 |

→ **4 个 writer / 4 个 owner = competing canonical writers (F4 P0-1 实质)**

## 2. Evidence owner

| 账本 | Writer | Owner | Reader |
|---|---|---|---|
| ev-* EvidenceBundle | EvidenceBuilder / orchestrator(M3) | EvidenceStore | CLI / backlog_sweeper |

单 owner (无多 SSOT), 但语义 = M3 审批包。

## 3. Verification (F3) owner

ver-*: verification_domain.materialize_verification 唯一 (F3 PASS, 无冲突)

## 4. I8 契约违反 (实际)

S2 Invariant I8: "外部 Executor 不能绕过 Artifact Lifecycle (产物必须走
GENERATED→…→COMMITTED)" — 但真实外部执行产物 (exec ART-*/EXS patch, 225+75)
**从未走 S2 lifecycle** (art-* 0 数据)。契约声明与现实执行完全脱节。

## 5. 结论

Artifact canonical owner 不存在 (4 竞争写者); Evidence owner 单套但语义错位;
Verification owner 唯一 (F3 已解决)。F4 的 Artifact 部分实质是 owner 统一问题,
需架构决策。
