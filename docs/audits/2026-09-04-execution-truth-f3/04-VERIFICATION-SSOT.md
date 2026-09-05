# 04 — VERIFICATION SSOT (P0-F3, 2026-09-04)

> 实现说明 — 单事实源

---

## 1. 新文件

`factory-console/verification_domain.py` — Verification SSOT domain:

```
get_verification(root, verification_id)      → dict | None (读单条)
list_verifications(root, task_run_id="", exs_id="")  → list (读/过滤)
count(root)                                  → int
materialize_verification(root, *, task_run_id, exs_id,
                         status, verification_type, method, result,
                         evidence_ref, attempt, detail, actor, note) → dict
  - status 规范化 (小写→大写; 空/非法 → ValueError)
  - 幂等: 同 (task_run_id, attempt, verification_type) → 返回已有
  - 原子写: tmp + os.replace
  - 损坏响亮失败
emit_audit(root, rec, event)                 → observation (VERIFICATION_*)
```

持久化: `<root>/verifications/verifications.json`
`{"verifications": {ver-xxx: {...}}}` (排序 + 原子写)

## 2. 修改文件

`factory-console/node_runtime.py`:
- 新增 `_materialize_verify()` — verify metadata → ver-* (单向)
  - 兼容 result/status 字段 (gateway verify dict 用 result;
    verify_code_with_pytest 用 status)
  - ok=False → FAIL; ok=True + pass → PASS; unknown/空 → UNKNOWN (禁止默认 PASS)
  - 失败安全 (物化失败 → 空引用, 不阻断 run 终态)
- `finalize_node_run()`: success/failure 分支 → run.verification = 引用
- `execute_node_run()`: verification 记录段 → 引用 + attempts 保留历史 + ver-* 物化

`factory-console/web/backend/fastapi_adapter.py`: T-9 溯源 EXS 命中时,
EXS.task_run_id 存在 → 投影 ver-* 到 trace["verifications"] (只读)

`factory-console/cli_factory.py`: `factory verification list|get` (F3 CLI 契约)

## 3. 不改

EXS model / Task model / TaskRun model (语义冻结) — ver-* 独立对象挂引用。
production_evaluation/production_experience 只读兼容 (fv.get("status") or fv.get("result"))。
release 域验证独立。

## 4. 迁移

无历史迁移: 旧 EXS/run 无 ver-* → store 空 (UNKNOWN/absent), 不 retroactive 伪造。
