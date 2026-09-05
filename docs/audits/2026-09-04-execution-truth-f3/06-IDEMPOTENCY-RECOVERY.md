# 06 — IDEMPOTENCY & RECOVERY (P0-F3, 2026-09-04)

---

## 1. Idempotency (F3 §12)

### 契约

```
one (task_run_id, attempt, verification_type) → one ver-* (canonical)
不同 attempt → 各自 ver-* (recovery/rerun 历史保留, 不覆盖)
不同 verification_type → 独立事实 (执行验证 vs pytest), 合法共存
```

### 实现

materialize_verification: 同键已存在 → 返回已有 (不双写)。
node_runtime finalize 幂等短路 (COMPLETED/FAILED → 返回现状, 不重复物化)。

### 测试/E2E

- F3 unit: test_repeat_same_attempt_single_record (同 attempt 同 type → 1 条)
- F3 unit: test_repeat_finalize_no_duplicate_ver (finalize ×2 → 单 ver-*)
- E2E-3: 同 pytest type+attempt → 同一 ver-*; 跨 type 独立

## 2. Recovery (F3 §13)

```
TaskRun-1 (attempt1) → ver-1 FAIL
    ↓ recovery (failed→ready→in_progress, 新 run)
TaskRun-2 (attempt2) → ver-2 PASS
```

- 身份不串: ver.task_run_id 各自指向 run-1/run-2 (E2E-4 + unit test_new_run_new_ver)
- 同一 run 多 attempt (execute_node_run repair): attempts 内嵌历史 + 每 attempt
  物化 ver-* (attempt 字段区分), 最终 run.verification = 最后引用
- 不覆盖历史: 不同 attempt → 不同 ver-* (test_different_attempt_separate_records)

## 3. 审计 (F3 §14)

- emit_audit: VERIFICATION_* 观察事件 (创建/完成) — audit 是 observation
- 禁止从 audit 推断 Verification 状态 (domain → audit 单向)
- AuditEvent 类型: 沿用 NODE_RUN_VERIFYING + VERIFICATION_* (observation)

## 4. 边界

- 旧 EXS/run 无 ver-* → store 空 (UNKNOWN/absent) — 不 retroactive
- F2 finalize 的 verify dict 无独立 ver-* id (旧数据) → run.verification 为空引用,
  EXS.verify 仍保留 (历史元数据) — 不迁移
