# 01 — D1 ARTIFACT CANONICAL (P0-F4 DECISION, 2026-09-05)

> D1 = APPROVED: Canonical Artifact = S2 art-* domain

---

## 1. 冻结决策

**Canonical Artifact = S2 art-* domain (artifact_lifecycle.py)**

- 唯一 canonical Artifact identity: `art-{uuid4.hex[:12]}`
- 唯一 lifecycle: S2 8 态 (GENERATED→STAGED→REVIEWED→APPROVED→APPLIED→VALIDATED→
  COMMITTED→RELEASED) + FAILURE_STATES (FAILED/REJECTED/REPAIRING/BLOCKED/CANCELLED)
- 唯一 writer: artifact_lifecycle (create/transition/approve/apply/validate/fail;
  模块级 _lock 串行)
- 唯一 repository: 前缀分片文件 `<root>/artifacts/xx/art-*.json` (I10 不可变,
  修改=新 version)
- 契约: I1-I12 invariants + APPROVAL_GATES (APPLIED/COMMITTED/RELEASED) +
  EVIDENCE_REQUIRED_TRANSITIONS (APPLIED/COMMITTED/RELEASED)

当前真实数据 0 条不改变 canonical owner 判断 (domain 完整性由 I1-I12 + 测试锁定,
零数据 = 从未接入真实执行, 非 domain 缺陷)。

## 2. 不得升级为 canonical

| 账本 | 定义 |
|---|---|
| factory-exec ART-* (exec/artifacts.json, 225) | LEGACY / ADAPTER (AgentRuntime 快照) |
| org ArtifactRegistry (org/artifacts.json, 24) | HISTORICAL PROJECTION (M3/S14 项目域) |
| EXS patch files (exec/patches/, 75) | LEGACY 外置产物 (文件名非 FK) |

## 3. 禁止

- 创建第五套 Artifact store
- ART-* / org registry / EXS patch filename 宣布为 canonical
- 为闭环伪造历史 art-* records
- 用文件名/audit/时间推断 identity

## 4. 关键问题回答 (S2 art-*)

1. identity: art-{uuid4.hex[:12]} (artifact_lifecycle.py:117)
2. lifecycle 8 态: GENERATED→STAGED→REVIEWED→APPROVED→APPLIED→VALIDATED→
   COMMITTED→RELEASED (全序; 失败态独立)
3. 唯一 canonical writer: artifact_lifecycle 模块函数 (create/transition/…,
   _lock 保护)
4. repository: `<root>/artifacts/{前缀2}/art-*.json` 分片不可变文件
5. 创建: create_artifact (强制 GENERATED 起步)
6. task_run_id/exs_id 获取: task_run_id = node_run_id (已有字段, run-*);
   exs_id = **当前无参数, F4 implementation 需给 create_artifact 增加 exs_id
   可选参数** (向后兼容)
7. idempotency: I10 不可变 + 唯一 id (每次 create 新 art-*; 同内容重复 =
   新 version/新记录 — 由调用方去重, 或用 content hash 检查 (F4 impl 定义))
8. creation failure: 抛 ArtifactError → 调用方 (node_runtime) 捕获 → run FAILED
   (现有模式, node_runtime.py:441-447)
9. lifecycle failure: fail_artifact (任何非终态→FAILED, 带证据, 不可回主链);
   非法转换抛 ArtifactError
10. 多 Artifact ↔ 1 TaskRun: **允许** (每次 execute_node_run attempt 产新
    artifact, I10 不可变; attempts 天然多 artifact)
11. 多 Artifact ↔ 1 EXS: **允许** (一个外部执行可产多个产物 — F4 impl 需挂同
    exs_id)
12. 避免旁路 ART-*: D4 I8 enforcement — production path 产物必须经
    create_artifact (见 04-D4-I8-ENFORCEMENT.md)
